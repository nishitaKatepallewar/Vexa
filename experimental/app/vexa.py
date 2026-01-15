import asyncio
import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in .env file.")
    sys.exit(1)

# Helper: Convert MCP Tool to Gemini Tool
def mcp_tool_to_gemini(mcp_tool) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=mcp_tool.name,
        description=mcp_tool.description,
        parameters=mcp_tool.inputSchema
    )

async def main():
    # Connect to Blender MCP Server

    print(f"Connecting to Blender Server module")

    server_params = StdioServerParameters(
        command="python3",  
        args=["-m", "blender_mcp.server"], 
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Fetch Tools from Blender
            try:
                tools_result = await session.list_tools()
                mcp_tools = tools_result.tools
                print(f"Connected! Vexa has loaded {len(mcp_tools)} 3D tools.")
            except Exception as e:
                print(f"Connection Error: Could not list tools. Is Blender open and the Addon running? \nError: {e}")
                return

            # Define Gemini Tools
            gemini_tools = [
                types.Tool(
                    function_declarations=[mcp_tool_to_gemini(t) for t in mcp_tools]
                )
            ]

            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Start the Chat Loop
            chat_history = []
            print("\n🤖 Vexa is listening... (Type 'exit' to quit)")
            print("   Try: 'Create a monkey' or 'Rotate the monkey 45 degrees'")

            while True:
                user_input = input("\nYou: ")
                if user_input.lower() in ["exit", "quit"]:
                    break

                # Add user message to history
                chat_history.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_input)]
                ))

                try:
                    # Send to Gemini
                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=chat_history,
                        config=types.GenerateContentConfig(
                            tools=gemini_tools,
                            temperature=0 
                        )
                    )

                    # Process Response
                    model_response_content = response.candidates[0].content
                    # Don't append immediately, wait to see if it's valid
                    chat_history.append(model_response_content) 

                    function_call = None
                    if model_response_content.parts:
                        for part in model_response_content.parts:
                            if part.function_call:
                                function_call = part.function_call
                                break

                    if function_call:
                        # --- TOOL EXECUTION BLOCK ---
                        tool_name = function_call.name
                        tool_args = function_call.args
                        print(f"Vexa is executing: {tool_name}...")

                        try:
                            # Run the tool in Blender
                            result = await session.call_tool(tool_name, arguments=tool_args)
                            tool_output = result.content[0].text
                            
                            print(f"Blender Output: {tool_output}")
                            
                            # Create the Function Response part
                            function_response_part = types.Part.from_function_response(
                                name=tool_name,
                                response={"result": tool_output}
                            )
                            
                            # Append the result to history
                            chat_history.append(types.Content(
                                role="user",
                                parts=[function_response_part]
                            ))

                            # Ask Gemini for the final natural language response
                            final_response = client.models.generate_content(
                                model="gemini-2.0-flash",
                                contents=chat_history
                            )
                            
                            final_text = final_response.text
                            print(f"🤖 Vexa: {final_text}")
                            
                            chat_history.append(types.Content(
                                role="model",
                                parts=[types.Part.from_text(text=final_text)]
                            ))

                        except Exception as e:
                            print(f"Tool Execution Error: {e}")
                    else:
                        # --- NORMAL CHAT BLOCK ---
                        print(f"🤖 Vexa: {response.text}")
                
                except Exception as e:
                     print(f"Gemini Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
