import tkinter as tk
from tkinter import filedialog
import webbrowser
import sys
import os

def display_files_in_browser(file_path1, file_path2):
    # 파일 내용을 읽어와서 HTML 형식으로 변환
    content1 = ""
    content2 = ""
    try:
        with open(file_path1, 'r', encoding='utf-8') as f:
            content1 = f.read()
        with open(file_path2, 'r', encoding='utf-8') as f:
            content2 = f.read()
    except FileNotFoundError:
        print("파일을 찾을 수 없습니다.")
        return
    except Exception as e:
        print(f"파일 읽기 오류: {e}")
        return

    html_content = f"""
    <html>
    <head>
        <title>파일 내용 보기</title>
        <style>
            body {{ font-family: sans-serif; display: flex; }}
            .file-container {{ flex: 1; margin: 10px; padding: 15px; border: 1px solid #ccc; background-color: #f9f9f9; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; }}
        </style>
    </head>
    <body>
        <div class="file-container">
            <h2>파일 1: {os.path.basename(file_path1)}</h2>
            <pre>{content1}</pre>
        </div>
        <div class="file-container">
            <h2>파일 2: {os.path.basename(file_path2)}</h2>
            <pre>{content2}</pre>
        </div>
    </body>
    </html>
    """

    # 임시 HTML 파일 생성
    temp_html_file = "temp_display_files.html"
    with open(temp_html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 웹 브라우저로 열기
    webbrowser.open(temp_html_file)

    # 임시 파일 삭제 (선택 사항)
    # os.remove(temp_html_file)

def browse_files():
    file_paths = filedialog.askopenfilenames() # 여러 파일 선택 가능
    if len(file_paths) == 2:
        display_files_in_browser(file_paths[0], file_paths[1])
    elif len(file_paths) > 2:
        print("두 개의 파일만 선택해주세요.")
    else:
        print("두 개의 파일을 선택해야 합니다.")

def main():
    if len(sys.argv) == 3: # 명령줄 인자로 두 개의 파일 경로를 받은 경우
        file_path1 = sys.argv[1]
        file_path2 = sys.argv[2]
        display_files_in_browser(file_path1, file_path2)
    else: # GUI를 통해 파일 선택
        root = tk.Tk()
        root.withdraw() # 메인 Tk 창 숨기기
        browse_files()
        root.destroy()

if __name__ == "__main__":
    main()