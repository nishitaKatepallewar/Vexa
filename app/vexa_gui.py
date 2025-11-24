import asyncio
import os
import sys
import flet as ft
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- CONFIGURATION ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BLENDER_MCP_PATH = os.path.join(CURRENT_DIR, "blender-mcp")

# --- HELPER FUNCTIONS ---
def mcp_tool_to_gemini(mcp_tool) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=mcp_tool.name,
        description=mcp_tool.description,
        parameters=mcp_tool.inputSchema
    )

async def main(page: ft.Page):
    print("🚀 Vexa App Starting...")
    
    # --- UI SETUP ---
    page.title = "Vexa 3D Architect"
    page.theme_mode = "dark"
    page.window_width = 500
    page.window_height = 800
    
    # 1. Create Layout Containers
    chat_list = ft.ListView(
        expand=True, 
        spacing=10, 
        auto_scroll=True,
        padding=20
    )
    
    status_text = ft.Text("Connecting to Blender...", color="yellow")

    # 2. Define Input Box (needed by send_message)
    input_box = ft.TextField(
        hint_text="Describe what to build (e.g. 'Create a red cube')...",
        expand=True,
        border_radius=20,
        shift_enter=True
    )

    # 3. State Variables
    chat_history = []
    gemini_client = None
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    # We use a mutable list to store the session so the inner function can access it
    state = {"session": None, "tools": []}

    # --- UI UPDATER ---
    def add_message(text, sender="user"):
        if sender == "user":
            align = "end"
            bg_color = "blue900"
        else:
            align = "start"
            bg_color = "green900"
        
        chat_list.controls.append(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(text, selectable=True),
                        padding=15,
                        border_radius=20,
                        bgcolor=bg_color,
                        width=300
                    )
                ],
                alignment=align
            )
        )
        page.update()

    # --- SEND MESSAGE LOGIC ---
    async def send_message(e):
        print("🔵 Send triggered...")
        user_text = input_box.value
        if not user_text:
            return
        
        # Clear UI immediately
        input_box.value = ""
        input_box.disabled = True
        add_message(user_text, "user")
        page.update()

        try:
            if not gemini_client:
                 add_message("❌ Error: API Key missing in .env", "vexa")
                 input_box.disabled = False
                 page.update()
                 return

            # Add to history
            chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

            print("🤖 Asking Gemini...")
            # 1. Ask Gemini
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=chat_history,
                config=types.GenerateContentConfig(tools=state["tools"], temperature=0)
            )

            model_content = response.candidates[0].content
            chat_history.append(model_content)

            # 2. Check for Function Call
            function_call = None
            if model_content.parts:
                for part in model_content.parts:
                    if part.function_call:
                        function_call = part.function_call
                        break

            if function_call:
                tool_name = function_call.name
                tool_args = function_call.args
                print(f"🛠️ Gemini requested tool: {tool_name}")
                
                add_message(f"🛠️ Executing: {tool_name}...", "vexa")
                
                # 3. Execute in Blender
                if state["session"]:
                    result = await state["session"].call_tool(tool_name, arguments=tool_args)
                    tool_output = result.content[0].text
                    print(f"✅ Blender Output: {tool_output}")
                    
                    # 4. Send result back to Gemini
                    function_response_part = types.Part.from_function_response(
                        name=tool_name,
                        response={"result": tool_output}
                    )
                    chat_history.append(types.Content(role="user", parts=[function_response_part]))
                    
                    final_response = gemini_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=chat_history
                    )
                    add_message(final_response.text, "vexa")
                    chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_response.text)]))
                else:
                    add_message("❌ Error: Blender is not connected.", "vexa")

            else:
                # Normal Text Response
                add_message(response.text, "vexa")

        except Exception as ex:
            print(f"❌ Error in send_message: {ex}")
            add_message(f"Error: {str(ex)}", "vexa")
        
        # Re-enable input
        input_box.disabled = False
        input_box.focus()
        page.update()

    # 4. Attach Event Handler (Directly!)
    input_box.on_submit = send_message
    
    send_btn = ft.IconButton(
        icon="send_rounded",
        icon_color="blue400",
        tooltip="Send",
        on_click=send_message  # <--- Direct reference, no lambda
    )

    # 5. Build Page Layout
    page.add(
        ft.Container(
            content=ft.Row(
                [ft.Text("Vexa 3D", size=20, weight="bold"), status_text], 
                alignment="spaceBetween"
            ),
            padding=10,
            bgcolor="surfaceVariant"
        ),
        chat_list,
        ft.Container(
            content=ft.Row([input_box, send_btn]),
            padding=10
        )
    )

    # --- SERVER CONNECTION LOOP ---
    print("🔌 Attempting to connect to Blender MCP...")
    server_params = StdioServerParameters(
        command="python3",
        args=["-m", "blender_mcp.server"],
        env=os.environ.copy()
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                state["session"] = session # Save to state so send_message can use it
                await session.initialize()
                
                # Load tools
                tools_result = await session.list_tools()
                mcp_tools = tools_result.tools
                state["tools"] = [types.Tool(function_declarations=[mcp_tool_to_gemini(t) for t in mcp_tools])]
                
                print(f"✅ Connected! Loaded {len(mcp_tools)} tools.")
                
                # Update UI
                status_text.value = "🟢 Connected"
                status_text.color = "green"
                add_message("Hello! I am Vexa. Blender is connected.", "vexa")
                page.update()

                # Keep app alive
                while True:
                    await asyncio.sleep(0.1)
    except Exception as e:
        print(f"🔴 Connection Failed: {e}")
        status_text.value = "🔴 Connection Failed"
        status_text.color = "red"
        add_message(f"Could not connect to Blender MCP. Check terminal for details.", "vexa")
        page.update()

if __name__ == "__main__":
    ft.app(target=main)
