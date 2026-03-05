import json
import re
import difflib
import html
import cv2
import numpy as np
from playwright.sync_api import sync_playwright

def export_pixel_perfect_video(json_path, output_mp4="beautiful_animation.mp4"):
    # 1. Load Data
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    question = data['question']
    output_strs = data['output_str']
    is_corrector_list = data['is_corrector'] 
    
    TOKEN_REGEX = r'(<\|mdm_mask\|>|<\|endoftext\|>|\n| )'

    frames_html = []
    modes = []
    prev_tokens = []

    # 2. Tokenize and Diff Logic
    for i, text in enumerate(output_strs):
        current_tokens = [t for t in re.split(TOKEN_REGEX, text) if t]
        frame_spans = []
        
        # Read the explicit mode straight from your JSON
        is_corrector = is_corrector_list[i]
        
        # Only apply a highlight class if it is a corrector step
        highlight_class = "token-corrector" if is_corrector else ""
        
        if i == 0:
            for tok in current_tokens:
                if tok == '<|mdm_mask|>': frame_spans.append(' ') # Replace mask with whitespace
                elif tok == '<|endoftext|>': continue
                elif tok == '\n': frame_spans.append('<br>')
                elif tok.strip() == '': frame_spans.append('<span> </span>')
                else: frame_spans.append(f'<span>{html.escape(tok)}</span>')
            prev_tokens = current_tokens
            frames_html.append("".join(frame_spans))
            modes.append("Corrector" if is_corrector else "Denoiser")
            continue

        matcher = difflib.SequenceMatcher(None, prev_tokens, current_tokens)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for tok in current_tokens[j1:j2]:
                    if tok == '<|mdm_mask|>': frame_spans.append(' ')
                    elif tok == '<|endoftext|>': continue
                    elif tok == '\n': frame_spans.append('<br>')
                    elif tok.strip() == '': frame_spans.append('<span> </span>')
                    else: frame_spans.append(f'<span>{html.escape(tok)}</span>')
            elif tag in ('replace', 'insert'):
                for tok in current_tokens[j1:j2]:
                    if tok == '<|mdm_mask|>': frame_spans.append(' ')
                    elif tok == '<|endoftext|>': continue
                    elif tok == '\n': frame_spans.append('<br>')
                    elif tok.strip() == '': frame_spans.append('<span> </span>')
                    else: 
                        # Apply green highlight if correcting, otherwise just normal text
                        if highlight_class:
                            frame_spans.append(f'<span class="{highlight_class}">{html.escape(tok)}</span>')
                        else:
                            frame_spans.append(f'<span>{html.escape(tok)}</span>')
                    
        prev_tokens = current_tokens
        frames_html.append("".join(frame_spans))
        modes.append("Corrector" if is_corrector else "Denoiser")

    # 3. Build the Beautiful HTML String
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0; 
                padding: 20px; /* Tight borders on sides, moderate at top */
                background-color: #ffffff;
                display: flex; justify-content: center; 
                align-items: flex-start; /* LOCKS boxes to the top of the video */
                height: 100vh; box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
            .anim-container {{
                width: 100%; 
                max-width: 1240px; /* WIDE boxes to reduce horizontal gray space */
                line-height: 1.6;
            }}
            
            /* Shared Box Styles */
            .content-box {{
                background-color: #ffffff;
                padding: 24px 28px;
                border-radius: 0 10px 10px 0;
                box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            }}
            .section-label {{
                font-size: 0.9em; text-transform: uppercase; letter-spacing: 1.5px;
                color: #6a737d; font-weight: 700;
            }}

            /* Prompt Specifics */
            .prompt-box {{
                border-left: 6px solid #4a90e2; 
                margin-bottom: 24px;
            }}
            .prompt-text {{
                font-size: 1.35em; color: #24292e; margin: 12px 0 0 0; font-weight: 500;
            }}

            /* Response Specifics */
            .response-box {{
                border-left: 6px solid #10b981; 
                min-height: 120px; /* TIGHT height hugs the text */
                display: flex; flex-direction: column;
            }}
            .response-header {{
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #eaecef;
            }}
            .output-area {{
                font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
                white-space: pre-wrap; word-wrap: break-word;
                font-size: 18px; color: #24292e; line-height: 1.7; flex-grow: 1;
            }}

            /* iOS Style Toggle Switch */
            .mode-toggle {{
                position: relative; display: flex; background-color: #e1e4e8;
                border-radius: 40px; width: 240px; height: 42px;
                overflow: hidden; box-shadow: inset 0 2px 5px rgba(0,0,0,0.08);
            }}
            .toggle-slider {{
                position: absolute; top: 4px; left: 4px; width: 114px; height: 34px;
                background-color: #add8e6; border-radius: 30px;
                transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
                box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            }}
            .mode-toggle.corrector .toggle-slider {{
                transform: translateX(118px); background-color: #90ee90;
            }}
            .toggle-label {{
                flex: 1; display: flex; align-items: center; justify-content: center;
                z-index: 1; font-weight: 600; font-size: 14px; color: #586069; transition: color 0.3s;
            }}
            .mode-toggle.corrector .label-denoiser {{ color: #6a737d; font-weight: 500; }}
            .mode-toggle.corrector .label-corrector {{ color: #1b1f23; font-weight: 700; }}
            .mode-toggle:not(.corrector) .label-denoiser {{ color: #1b1f23; font-weight: 700; }}
            .mode-toggle:not(.corrector) .label-corrector {{ color: #6a737d; font-weight: 500; }}
            
            /* Token Styles */
            .token-corrector {{ background-color: #90ee90; border-radius: 5px; padding: 2px 4px; font-weight: 600; color: #005cc5; }}
        </style>
    </head>
    <body>
        <div class="anim-container">
            <div class="content-box prompt-box">
                <div class="section-label">PROMPT</div>
                <p class="prompt-text">{html.escape(question)}</p>
            </div>
            
            <div class="content-box response-box">
                <div class="response-header">
                    <div class="section-label">RESPONSE</div>
                    <div id="mode-toggle" class="mode-toggle">
                        <div class="toggle-slider"></div>
                        <div class="toggle-label label-denoiser">Denoiser</div>
                        <div class="toggle-label label-corrector">Corrector</div>
                    </div>
                </div>
                <div id="output-area" class="output-area"></div>
            </div>
        </div>
        
        <script>
            const frames = {json.dumps(frames_html)};
            const modes = {json.dumps(modes)};

            const outputArea = document.getElementById("output-area");
            const modeToggle = document.getElementById("mode-toggle");

            window.renderFrame = function(index) {{
                outputArea.innerHTML = frames[index];
                if (modes[index] === "Corrector") {{
                    modeToggle.classList.add("corrector");
                }} else {{
                    modeToggle.classList.remove("corrector");
                }}
            }};
            window.renderFrame(0);
        </script>
    </body>
    </html>
    """

    print("Launching Chromium to render frames... (this might take a few seconds)")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720}) 
        page.set_content(html_template)

        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        fps = 30
        video = cv2.VideoWriter(output_mp4, fourcc, fps, (1280, 720))

        if not video.isOpened():
            raise RuntimeError("OpenCV failed to open the video file. Check permissions!")

        total_steps = len(frames_html)

        for step in range(total_steps):
            page.evaluate(f"window.renderFrame({step})")

            for _ in range(24):
                screenshot_bytes = page.screenshot(type='jpeg', quality=100)
                nparr = np.frombuffer(screenshot_bytes, np.uint8)
                cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                video.write(cv_img)
                page.wait_for_timeout(33) 

        # Hold on the final completed state for 3 extra seconds
        for _ in range(90):
            screenshot_bytes = page.screenshot(type='jpeg', quality=100)
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            video.write(cv_img)
            page.wait_for_timeout(33)

        video.release()
        browser.close()

    print(f"High Quality Video successfully exported to: {output_mp4}")


if __name__ == "__main__":
    doc_id = 92
    export_pixel_perfect_video(
        f"intermediate_outputs{doc_id}.json",
        f"generation{doc_id}.mp4"
    )
