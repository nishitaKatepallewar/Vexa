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
    page.title = "Vexa"
    page.theme_mode = "dark"
    page.padding = 0
    page.window_width = 500
    page.window_height = 800
    page.bgcolor = "#111111" # Very dark background

    # 1. Create Layout Containers
    chat_list = ft.ListView(
        expand=True, 
        spacing=15, 
        auto_scroll=True,
        padding=20
    )
    
    # Status indicator (Small square)
    status_indicator = ft.Container(width=10, height=10, bgcolor="yellow", tooltip="Connecting...")
    status_text = ft.Text("Connecting...", size=12, color="grey")

    # 2. Define Input Box
    input_box = ft.TextField(
        hint_text="Command Vexa...",
        hint_style=ft.TextStyle(color="grey"),
        expand=True,
        border_radius=0, # Sharp corners
        border_color="#333333",
        bgcolor="#1a1a1a",
        filled=True,
        content_padding=15,
        shift_enter=True,
        text_style=ft.TextStyle(font_family="Roboto Mono") # Tech font look
    )

    # 3. State Variables
    chat_history = []
    gemini_client = None
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    state = {"session": None, "tools": []}

    # --- UI UPDATER ---
    def add_message(text, sender="user"):
        if sender == "user":
            align = "end"
            bg_color = "#152e4d" # Dark Technical Blue
            txt_color = "white"
            prefix = " YOU "
        else:
            align = "start"
            bg_color = "#262626" # Matte Dark Grey
            txt_color = "#e0e0e0"
            prefix = " VEXA "
        
        chat_list.controls.append(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Column([
                            # Tiny label above message
                            ft.Text(prefix, size=10, weight="bold", color="grey"),
                            ft.Text(text, selectable=True, color=txt_color, font_family="Roboto Mono", size=14)
                        ], spacing=2),
                        padding=15,
                        border_radius=0, # Sharp rectangles
                        bgcolor=bg_color,
                        width=320,
                        # FIX: Using proper BorderSide syntax
                        border=ft.border.all(1, "#333333") 
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

            chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

            print("🤖 Asking Gemini...")
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=chat_history,
                config=types.GenerateContentConfig(tools=state["tools"], temperature=0)
            )

            model_content = response.candidates[0].content
            chat_history.append(model_content)

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
                
                add_message(f"Running process: {tool_name}...", "vexa")
                
                if state["session"]:
                    result = await state["session"].call_tool(tool_name, arguments=tool_args)
                    tool_output = result.content[0].text
                    print(f"✅ Blender Output: {tool_output}")
                    
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
                add_message(response.text, "vexa")

        except Exception as ex:
            print(f"❌ Error in send_message: {ex}")
            add_message(f"Error: {str(ex)}", "vexa")
        
        input_box.disabled = False
        input_box.focus()
        page.update()

    # 4. Attach Event Handler
    input_box.on_submit = send_message
    
    # Square Send Button with String Icon
    send_btn = ft.Container(
        content=ft.Icon(name="arrow_forward", color="white"), # Using string name
        bgcolor="#152e4d", 
        padding=10,
        on_click=send_message,
        width=50,
        height=50,
        alignment=ft.alignment.center,
        border_radius=0 # Sharp square
    )

    # 5. Build Page Layout
    header = ft.Container(
        content=ft.Row(
            [
                ft.Text("VEXA", size=20, weight="bold", font_family="Roboto Mono"), 
                ft.Row([status_indicator, status_text], spacing=5)
            ], 
            alignment="spaceBetween"
        ),
        padding=ft.padding.symmetric(horizontal=20, vertical=15),
        bgcolor="#1a1a1a",
        # FIX: Using border.only with BorderSide
        border=ft.border.only(bottom=ft.BorderSide(1, "#333333"))
    )

    input_area = ft.Container(
        content=ft.Row([input_box, send_btn], spacing=0),
        padding=20,
        bgcolor="#111111"
    )

    page.add(
        header,
        ft.Container(content=chat_list, expand=True),
        input_area
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
                state["session"] = session
                await session.initialize()
                
                tools_result = await session.list_tools()
                mcp_tools = tools_result.tools
                state["tools"] = [types.Tool(function_declarations=[mcp_tool_to_gemini(t) for t in mcp_tools])]
                
                print(f"✅ Connected! Loaded {len(mcp_tools)} tools.")
                
                # Update Status UI
                status_indicator.bgcolor = "#00FF00" # Neon Green hex
                status_indicator.tooltip = "Connected"
                status_text.value = "ONLINE"
                status_text.color = "#00FF00"
                
                add_message("System Initialized. Blender Connected.", "vexa")
                page.update()

                while True:
                    await asyncio.sleep(0.1)
    except Exception as e:
        print(f"🔴 Connection Failed: {e}")
        status_indicator.bgcolor = "red"
        status_text.value = "OFFLINE"
        status_text.color = "red"
        add_message(f"Connection Error. Check terminal.", "vexa")
        page.update()

if __name__ == "__main__":
    ft.app(target=main)