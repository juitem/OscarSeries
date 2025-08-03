import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
import os
import re
import subprocess
import platform

class FileViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced Two-Panel Tabbed File Viewer (Bytes Version)")
        self.root.geometry("1400x800")

        # --- 컨트롤 프레임: 새 탭 생성 버튼 ---
        self.control_frame = tk.Frame(self.root)
        self.control_frame.pack(pady=10, fill=tk.X, padx=10)

        # 좌측 새 탭 버튼
        self.left_new_tab_button = tk.Button(self.control_frame, text="새 탭 (좌)",
                                             command=lambda: self.add_new_tab(self.left_notebook, "좌"))
        self.left_new_tab_button.pack(side=tk.LEFT, padx=(0, 5), anchor="w")

        # 우측 새 탭 버튼
        self.right_new_tab_button = tk.Button(self.control_frame, text="새 탭 (우)",
                                              command=lambda: self.add_new_tab(self.right_notebook, "우"))
        self.right_new_tab_button.pack(side=tk.RIGHT, padx=(5, 0), anchor="e")

        # --- 메인 컨텐츠 프레임: 탭 뷰 ---
        self.tab_view_frame = tk.Frame(self.root)
        self.tab_view_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        # 좌측 노트북 (탭 컨트롤)
        self.left_notebook = ttk.Notebook(self.tab_view_frame)
        self.left_notebook.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 5))

        # 우측 노트북 (탭 컨트롤)
        self.right_notebook = ttk.Notebook(self.tab_view_frame)
        self.right_notebook.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH, padx=(5, 0))

        self.tab_info_map = {}
        self.tab_index_counter = {'left': 1, 'right': 1} 
        
        # --- 자동 업데이트 모니터링을 위한 의존성 맵 ---
        # {소스_탭_id: [의존_탭_id1, 의존_탭_id2, ...]}
        self.dependency_map = {} 
        self.root.after(1000, self.check_for_auto_updates) # 1초마다 주기적 검사 시작

        # 초기 탭 생성
        self.add_new_tab(self.left_notebook, "좌")
        self.add_new_tab(self.right_notebook, "우")

    def add_new_tab(self, notebook_widget, side_name):
        new_frame = ttk.Frame(notebook_widget)
        
        side_key = "left" if notebook_widget == self.left_notebook else "right"
        
        tab_suffix = self.tab_index_counter[side_key]
        self.tab_index_counter[side_key] += 1

        initial_tab_type = "normal"
        
        notebook_widget.add(new_frame, text="새 탭...") # 임시 탭 이름
        
        if notebook_widget not in self.tab_info_map:
            self.tab_info_map[notebook_widget] = {}
        
        include_regex_var = tk.StringVar()
        exclude_regex_var = tk.StringVar()
        regex_var = tk.StringVar()
        replace_var = tk.StringVar()
        start_regex_var = tk.StringVar()
        end_regex_var = tk.StringVar()
        source_tab_var = tk.StringVar()
        
        # Cmdline 관련 변수
        command_input_var = tk.StringVar()
        cmd_f_var = tk.StringVar() 
        cmd_u_var = tk.StringVar() 
        current_working_directory = os.getcwd() 

        # 자동 업데이트 변수 (기본값 True)
        auto_update_var = tk.BooleanVar(value=True) 

        tab_info = {
            'type': initial_tab_type, 
            'source_content': b'', # 바이트로 저장
            'current_display_content': b'', # 바이트로 저장
            'display_widget': None,
            'include_regex': include_regex_var,
            'exclude_regex': exclude_regex_var,
            'regex_pattern': regex_var,
            'replace_string': replace_var,
            'start_regex': start_regex_var,
            'end_regex': end_regex_var,
            'status_label': None,
            'tab_source_var': tk.StringVar(new_frame), 
            'selected_source_tab': source_tab_var, 
            'parent_notebook': notebook_widget,
            'tab_content_frame_id': str(new_frame),
            'dynamic_ui_elements': {},
            'tab_index_suffix': tab_suffix, 
            'side_name': side_name,
            
            # Cmdline 전용 정보
            'cmd_input_var': command_input_var,
            'cmd_f_var': cmd_f_var,
            'cmd_u_var': cmd_u_var,
            'current_cwd': current_working_directory,
            'cmd_input_entry': None, 
            'cmd_run_button': None, 
            'cmd_ui_frame': None, 
            'cmd_f_entry': None, 
            'cmd_u_entry': None, 
            
            # 자동 업데이트 정보
            'auto_update_var': auto_update_var,
            'auto_update_checkbox': None, 
            'last_source_content_hash': None, 
            
            # 탭 종류 변경 메뉴 참조
            'tab_type_menu': None,
        }
        self.tab_info_map[notebook_widget][str(new_frame)] = tab_info

        # --- 탭 내부의 상단 컨트롤 프레임 ---
        control_sub_frame = tk.Frame(new_frame)
        control_sub_frame.pack(fill=tk.X, padx=5, pady=5)

        # 소스 선택 메뉴
        tab_info['tab_source_var'].set("직접 텍스트 입력")
        tab_source_options = ["파일에서 로드", "직접 텍스트 입력", "다른 탭에서 가져오기", "Cmdline"]
        tab_source_menu = tk.OptionMenu(control_sub_frame, tab_info['tab_source_var'], *tab_source_options,
                                        command=lambda opt, f=new_frame, n=notebook_widget: self.on_tab_source_change(n, f, opt))
        tab_source_menu.pack(side=tk.LEFT, padx=(0, 10))

        # 소스 탭 선택 드롭다운 (초기에는 숨김)
        tab_info['source_tab_selection_frame'] = tk.Frame(control_sub_frame)
        tab_info['source_tab_selection_frame'].pack(side=tk.LEFT, padx=(0, 5))
        
        tab_info['source_tab_menu'] = tk.OptionMenu(tab_info['source_tab_selection_frame'], tab_info['selected_source_tab'], "")
        tab_info['source_tab_menu'].pack(side=tk.LEFT)
        tab_info['source_tab_selection_frame'].pack_forget()

        # '가져오기' 버튼
        tab_info['get_source_tab_button'] = tk.Button(tab_info['source_tab_selection_frame'], text="가져오기",
                                                command=lambda n=notebook_widget, f=new_frame: self.get_content_from_other_tab(n, f))
        tab_info['get_source_tab_button'].pack(side=tk.LEFT, padx=(5,0))
        tab_info['source_tab_selection_frame'].pack_forget()

        # 자동 업데이트 체크 버튼
        tab_info['auto_update_checkbox'] = tk.Checkbutton(
            tab_info['source_tab_selection_frame'],
            text="자동 업데이트",
            variable=tab_info['auto_update_var'],
            command=lambda n=notebook_widget, f=new_frame: self.toggle_auto_update(n, f)
        )
        tab_info['auto_update_checkbox'].pack(side=tk.LEFT, padx=(5,0))
        tab_info['auto_update_checkbox'].pack_forget()

        # 탭 종류 변경 메뉴
        tab_info['tab_type_var'] = tk.StringVar(new_frame)
        tab_info['tab_type_var'].set(self.get_display_tab_type(initial_tab_type)) 
        
        tab_type_options = ["일반 탭으로 전환", "필터 탭으로 전환", "치환 탭으로 전환", "라인 캡쳐 탭으로 전환"]
        tab_type_menu = tk.OptionMenu(control_sub_frame, tab_info['tab_type_var'], *tab_type_options,
                                      command=lambda opt, f=new_frame, n=notebook_widget: self.change_tab_type(n, f, opt))
        tab_type_menu.pack(side=tk.LEFT, padx=(10, 0))
        tab_info['tab_type_menu'] = tab_type_menu 

        # 탭 닫기 버튼
        close_tab_button = tk.Button(control_sub_frame, text="탭 닫기", 
                                     command=lambda nb=notebook_widget, frame=new_frame: self.close_tab_from_button(nb, frame))
        close_tab_button.pack(side=tk.RIGHT, padx=(10, 0))

        # --- 동적 UI 요소 프레임 (정규식/치환/라인캡쳐 필드) ---
        tab_info['dynamic_ui_elements_frame'] = tk.Frame(new_frame)
        tab_info['dynamic_ui_elements_frame'].pack(fill=tk.X, padx=5, pady=5)
        
        # 모든 가능한 동적 UI 요소를 생성하지만, 초기에는 숨김
        self.create_dynamic_ui_elements(tab_info)
        
        # 텍스트 위젯 (주요 내용 표시 영역)
        text_widget = scrolledtext.ScrolledText(new_frame, wrap=tk.WORD)
        text_widget.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        text_widget.config(state='normal') 
        tab_info['display_widget'] = text_widget
        
        # '직접 텍스트 입력' 탭에서 키 입력 시 소스 내용 업데이트
        text_widget.bind("<KeyRelease>", lambda e, n=notebook_widget, f=new_frame: self.update_source_content_on_key_release(n, f))

        # --- 상태 라벨 프레임 (하단으로 이동) ---
        # NOTE: 상태 라벨을 뷰의 가장 아래쪽으로 옮기기 위해 새로운 프레임에 담아 pack(side=tk.BOTTOM)을 사용합니다.
        status_frame = tk.Frame(new_frame)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        
        tab_status_label = tk.Label(status_frame, text="", anchor="w") 
        tab_status_label.pack(side=tk.LEFT, expand=True, fill=tk.X)
        tab_info['status_label'] = tab_status_label

        notebook_widget.select(new_frame)
        
        tab_info['current_display_content'] = b''
        tab_info['source_content'] = b'' 

        # 초기 상태 업데이트
        self.update_tab_display(notebook_widget, new_frame)
        self.update_status_label(notebook_widget, new_frame) 
        self._update_tab_name(notebook_widget, new_frame) 

    def _update_tab_name(self, notebook_widget, tab_frame):
        """탭의 표시 이름을 현재 상태에 맞게 업데이트합니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        
        side_name = current_tab_info['side_name']
        tab_suffix = current_tab_info['tab_index_suffix']
        tab_source_type = current_tab_info['tab_source_var'].get()
        tab_logic_type = current_tab_info['type']
        
        tab_kind_map = {
            "normal": "일반",
            "filter": "필터",
            "replace": "치환",
            "line_capture": "캡쳐",
        }
        tab_kind_str = ""
        if tab_source_type == "Cmdline":
            tab_kind_str = "Cmd"
        else:
            tab_kind_str = tab_kind_map.get(tab_logic_type, "일반")
        
        is_source_tab = (tab_source_type == "직접 텍스트 입력" or tab_source_type == "파일에서 로드")
        
        parts = []
        if is_source_tab:
            parts.append("소스")
        parts.append(tab_kind_str)
        
        name_details = ", ".join(parts)
        
        new_tab_name = f"{side_name}{tab_suffix}({name_details})"
        
        current_tab_index = notebook_widget.index(tab_frame)
        notebook_widget.tab(current_tab_index, text=new_tab_name)

    def create_dynamic_ui_elements(self, tab_info):
        """모든 동적 UI 요소를 생성하고, 초기에 숨깁니다."""
        dynamic_frame = tab_info['dynamic_ui_elements_frame']
        
        # --- 필터 탭 UI 요소 ---
        filter_elements = {}
        filter_frame = tk.Frame(dynamic_frame) 
        lbl1 = tk.Label(filter_frame, text="포함 정규식:")
        entry1 = tk.Entry(filter_frame, textvariable=tab_info['include_regex'], width=30)
        entry1.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_filter(n, self.get_frame_from_id(n, f)))
        lbl2 = tk.Label(filter_frame, text="삭제 정규식:")
        entry2 = tk.Entry(filter_frame, textvariable=tab_info['exclude_regex'], width=30)
        entry2.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_filter(n, self.get_frame_from_id(n, f)))
        btn = tk.Button(filter_frame, text="적용", 
                         command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_filter(n, self.get_frame_from_id(n, f)))
        filter_elements['frame'] = filter_frame
        filter_elements['widgets'] = [lbl1, entry1, lbl2, entry2, btn]
        tab_info['dynamic_ui_elements']['filter'] = filter_elements

        # --- 치환 탭 UI 요소 ---
        replace_elements = {}
        replace_frame = tk.Frame(dynamic_frame) 
        lbl1 = tk.Label(replace_frame, text="정규식:")
        entry1 = tk.Entry(replace_frame, textvariable=tab_info['regex_pattern'], width=30)
        entry1.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_regex(n, self.get_frame_from_id(n, f)))
        lbl2 = tk.Label(replace_frame, text="치환 문자열:")
        entry2 = tk.Entry(replace_frame, textvariable=tab_info['replace_string'], width=30)
        entry2.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_regex(n, self.get_frame_from_id(n, f)))
        btn = tk.Button(replace_frame, text="적용",
                         command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_regex(n, self.get_frame_from_id(n, f)))
        replace_elements['frame'] = replace_frame
        replace_elements['widgets'] = [lbl1, entry1, lbl2, entry2, btn]
        tab_info['dynamic_ui_elements']['replace'] = replace_elements

        # --- 라인 캡쳐 탭 UI 요소 ---
        line_capture_elements = {}
        line_capture_frame = tk.Frame(dynamic_frame) 
        lbl1 = tk.Label(line_capture_frame, text="START 정규식:")
        entry1 = tk.Entry(line_capture_frame, textvariable=tab_info['start_regex'], width=25)
        entry1.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_line_capture(n, self.get_frame_from_id(n, f)))
        lbl2 = tk.Label(line_capture_frame, text="END 정규식:")
        entry2 = tk.Entry(line_capture_frame, textvariable=tab_info['end_regex'], width=25)
        entry2.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_line_capture(n, self.get_frame_from_id(n, f)))
        btn = tk.Button(line_capture_frame, text="적용",
                         command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_line_capture(n, self.get_frame_from_id(n, f)))
        line_capture_elements['frame'] = line_capture_frame
        line_capture_elements['widgets'] = [lbl1, entry1, lbl2, entry2, btn]
        tab_info['dynamic_ui_elements']['line_capture'] = line_capture_elements

        # --- Cmdline 탭 UI 요소 ---
        cmdline_elements = {}
        cmdline_frame = tk.Frame(dynamic_frame) 
        cmd_input_frame = tk.Frame(cmdline_frame)
        cmd_input_frame.pack(fill=tk.X, pady=(0, 2))
        cmd_label = tk.Label(cmd_input_frame, text="명령어:")
        cmd_label.pack(side=tk.LEFT)
        cmd_entry = tk.Entry(cmd_input_frame, textvariable=tab_info['cmd_input_var'], width=60)
        cmd_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        cmd_entry.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.execute_command(n, self.get_frame_from_id(n, f)))
        cmd_button = tk.Button(cmd_input_frame, text="실행",
                               command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.execute_command(n, self.get_frame_from_id(n, f)))
        cmd_button.pack(side=tk.LEFT)
        f_input_frame = tk.Frame(cmdline_frame)
        f_input_frame.pack(fill=tk.X, pady=(0, 2))
        f_label = tk.Label(f_input_frame, text="%f:")
        f_label.pack(side=tk.LEFT)
        f_entry = tk.Entry(f_input_frame, textvariable=tab_info['cmd_f_var'], width=60)
        f_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        u_input_frame = tk.Frame(cmdline_frame)
        u_input_frame.pack(fill=tk.X, pady=(0, 2))
        u_label = tk.Label(u_input_frame, text="%u:")
        u_label.pack(side=tk.LEFT)
        u_entry = tk.Entry(u_input_frame, textvariable=tab_info['cmd_u_var'], width=60)
        u_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        tab_info['cmd_ui_frame'] = cmdline_frame
        tab_info['cmd_input_entry'] = cmd_entry
        tab_info['cmd_run_button'] = cmd_button
        tab_info['cmd_f_entry'] = f_entry 
        tab_info['cmd_u_entry'] = u_entry 

    def get_frame_from_id(self, notebook_widget, frame_id_str):
        """문자열 ID로 프레임 위젯을 가져오는 헬퍼 함수입니다."""
        for tab_id in notebook_widget.tabs():
            tab_frame = notebook_widget.nametowidget(tab_id)
            if str(tab_frame) == frame_id_str:
                return tab_frame
        return None 

    def hide_all_dynamic_ui(self, tab_info):
        """주어진 탭의 모든 동적 UI 요소를 숨깁니다."""
        for tab_type, elements in tab_info['dynamic_ui_elements'].items():
            if 'frame' in elements: 
                elements['frame'].pack_forget() 
        if tab_info['cmd_ui_frame']:
            tab_info['cmd_ui_frame'].pack_forget()
        if tab_info['auto_update_checkbox']:
            tab_info['auto_update_checkbox'].pack_forget()

    def show_tab_type_ui(self, notebook_widget, tab_frame, tab_type):
        """주어진 tab_type에 맞는 동적 UI 요소를 표시합니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        self.hide_all_dynamic_ui(current_tab_info) 

        # 소스 종류가 'Cmdline'인 경우, Cmdline 전용 UI를 표시합니다.
        if current_tab_info['tab_source_var'].get() == "Cmdline":
            if current_tab_info['cmd_ui_frame']:
                current_tab_info['cmd_ui_frame'].pack(fill=tk.X, padx=5, pady=5)
            return
        
        # 소스가 '다른 탭에서 가져오기'인 경우, 자동 업데이트 체크 버튼을 표시합니다.
        if current_tab_info['tab_source_var'].get() == "다른 탭에서 가져오기":
            if current_tab_info['auto_update_checkbox']:
                current_tab_info['auto_update_checkbox'].pack(side=tk.LEFT, padx=(5,0))

        # 다른 탭 종류에 따라 해당 UI를 표시합니다.
        if tab_type in current_tab_info['dynamic_ui_elements']:
            elements = current_tab_info['dynamic_ui_elements'][tab_type]
            if 'frame' in elements:
                elements['frame'].pack(fill=tk.X, padx=5, pady=5) 
                
                if tab_type == "filter":
                    elements['widgets'][0].pack(side=tk.LEFT) 
                    elements['widgets'][1].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 10)) 
                    elements['widgets'][2].pack(side=tk.LEFT) 
                    elements['widgets'][3].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 10)) 
                    elements['widgets'][4].pack(side=tk.RIGHT) 
                elif tab_type == "replace":
                    elements['widgets'][0].pack(side=tk.LEFT) 
                    elements['widgets'][1].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 10)) 
                    elements['widgets'][2].pack(side=tk.LEFT) 
                    elements['widgets'][3].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 10)) 
                    elements['widgets'][4].pack(side=tk.RIGHT) 
                elif tab_type == "line_capture":
                    elements['widgets'][0].pack(side=tk.LEFT) 
                    elements['widgets'][1].pack(side=tk.LEFT, padx=(5, 10)) 
                    elements['widgets'][2].pack(side=tk.LEFT) 
                    elements['widgets'][3].pack(side=tk.LEFT, padx=(5, 10)) 
                    elements['widgets'][4].pack(side=tk.RIGHT) 

    def get_actual_tab_type(self, display_text):
        """OptionMenu의 표시 텍스트를 내부 탭 유형 문자열로 변환합니다."""
        if "일반 탭" in display_text:
            return "normal"
        elif "필터 탭" in display_text:
            return "filter"
        elif "치환 탭" in display_text:
            return "replace"
        elif "라인 캡쳐 탭" in display_text:
            return "line_capture"
        return "normal" 

    def get_display_tab_type(self, actual_type):
        """내부 탭 유형 문자열을 OptionMenu의 표시 텍스트로 변환합니다."""
        if actual_type == "normal":
            return "일반 탭으로 전환"
        elif actual_type == "filter":
            return "필터 탭으로 전환"
        elif actual_type == "replace":
            return "치환 탭으로 전환"
        elif actual_type == "line_capture":
            return "라인 캡쳐 탭으로 전환"
        return "일반 탭으로 전환" 

    def change_tab_type(self, notebook_widget, tab_frame, selected_option_text):
        """현재 탭의 유형을 변경하고 UI를 업데이트합니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        new_tab_type = self.get_actual_tab_type(selected_option_text)
        current_tab_info['type'] = new_tab_type 
        current_tab_info['tab_type_var'].set(selected_option_text)

        self.show_tab_type_ui(notebook_widget, tab_frame, new_tab_type)
        self.update_tab_display(notebook_widget, tab_frame)
        self.update_status_label(notebook_widget, tab_frame) 
        self._update_tab_name(notebook_widget, tab_frame) 

    def on_tab_source_change(self, notebook_widget, tab_frame, selected_option):
        """탭 소스 선택 메뉴가 변경될 때 호출됩니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        text_widget = current_tab_info['display_widget']
        source_tab_selection_frame = current_tab_info['source_tab_selection_frame']
        
        # 소스 관련 모든 UI 요소를 먼저 숨깁니다.
        source_tab_selection_frame.pack_forget()
        if current_tab_info['cmd_ui_frame']:
            current_tab_info['cmd_ui_frame'].pack_forget()
        if current_tab_info['auto_update_checkbox']:
            current_tab_info['auto_update_checkbox'].pack_forget()

        text_widget.config(state='disabled')
        
        if current_tab_info['tab_source_var'].get() == "직접 텍스트 입력":
            current_tab_info['current_display_content'] = text_widget.get(1.0, tk.END).strip().encode('utf-8')
        else:
            current_tab_info['current_display_content'] = b'' 

        if selected_option != "Cmdline":
             current_tab_info['source_content'] = b''

        # 이전 소스의 의존성 목록에서 현재 탭을 제거합니다.
        self.remove_dependent_tab(current_notebook=notebook_widget, current_tab_frame=tab_frame)

        # 소스 종류에 따라 탭 종류 변경 메뉴의 활성화 상태를 제어합니다.
        if selected_option == "Cmdline":
            current_tab_info['tab_type_menu'].config(state=tk.DISABLED)
        else:
            current_tab_info['tab_type_menu'].config(state=tk.NORMAL)

        if selected_option == "파일에서 로드":
            file_path = filedialog.askopenfilename(
                title="파일 선택",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if file_path:
                content = b"" 
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    current_tab_info['source_content'] = content
                    self.update_tab_display(notebook_widget, tab_frame)
                except Exception as e:
                    content_str = f"파일 읽기 오류: {e}"
                    current_tab_info['source_content'] = b'' 
                    self.display_result(text_widget, content_str, state='disabled')
                    print(f"Error reading {file_path}: {e}")
            else:
                current_tab_info['tab_source_var'].set("직접 텍스트 입력") 
                current_tab_info['tab_type_menu'].config(state=tk.NORMAL) 
                current_tab_info['source_content'] = current_tab_info['current_display_content'] 
                self.update_tab_display(notebook_widget, tab_frame) 

        elif selected_option == "직접 텍스트 입력":
            text_widget.config(state='normal') 
            current_tab_info['source_content'] = current_tab_info['current_display_content'] 
            self.update_tab_display(notebook_widget, tab_frame)

        elif selected_option == "다른 탭에서 가져오기":
            source_tab_selection_frame.pack(side=tk.LEFT, padx=(0, 5))
            if current_tab_info['auto_update_checkbox']:
                current_tab_info['auto_update_checkbox'].pack(side=tk.LEFT, padx=(5,0))
            self.populate_source_tab_dropdown(notebook_widget, tab_frame)
            self.display_result(text_widget, "", state='disabled') 

        elif selected_option == "Cmdline":
            current_tab_info['cmd_ui_frame'].pack(fill=tk.X, padx=5, pady=5)
            self.display_result(text_widget, current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled') 
            
            if not current_tab_info['cmd_input_var'].get().strip() and not current_tab_info['current_display_content'].strip():
                if platform.system() == "Windows":
                    default_cmd = "dir /w/o-d/a"
                else:
                    default_cmd = "ls -alt"
                current_tab_info['cmd_input_var'].set(default_cmd)
                self.execute_command(notebook_widget, tab_frame)
            elif current_tab_info['cmd_input_var'].get().strip() and not current_tab_info['current_display_content'].strip():
                self.execute_command(notebook_widget, tab_frame)

        self.show_tab_type_ui(notebook_widget, tab_frame, current_tab_info['type'])
        self.update_status_label(notebook_widget, tab_frame) 
        self._update_tab_name(notebook_widget, tab_frame) 


    def populate_source_tab_dropdown(self, current_notebook, current_tab_frame):
        """소스 탭 선택 드롭다운 메뉴를 채웁니다."""
        current_tab_info = self.tab_info_map[current_notebook][str(current_tab_frame)]
        selected_source_tab_var = current_tab_info['selected_source_tab']
        source_tab_menu = current_tab_info['source_tab_menu']

        menu = source_tab_menu['menu']
        menu.delete(0, 'end')

        available_tabs = []
        for tab_id in current_notebook.tabs():
            tab_frame = current_notebook.nametowidget(tab_id)
            if str(tab_frame) in self.tab_info_map[current_notebook] and tab_frame != current_tab_frame:
                tab_name = self._get_simple_tab_name(current_notebook, tab_frame)
                available_tabs.append((tab_name, str(tab_frame), current_notebook))

        other_notebook = self.left_notebook if current_notebook == self.right_notebook else self.right_notebook
        for tab_id in other_notebook.tabs():
            tab_frame = other_notebook.nametowidget(tab_id)
            if str(tab_frame) in self.tab_info_map[other_notebook]:
                tab_name = self._get_simple_tab_name(other_notebook, tab_frame)
                available_tabs.append((tab_name, str(tab_frame), other_notebook))
        
        self.remove_dependent_tab(current_notebook, current_tab_frame)

        if not available_tabs:
            selected_source_tab_var.set("사용 가능한 탭 없음")
            menu.add_command(label="사용 가능한 탭 없음", state=tk.DISABLED)
            current_tab_info['get_source_tab_button'].config(state=tk.DISABLED)
            current_tab_info['auto_update_checkbox'].config(state=tk.DISABLED)
            current_tab_info['auto_update_var'].set(False)
            return

        selected_source_tab_var.set(available_tabs[0][0]) 
        
        for tab_name, tab_frame_str, notebook_ref in available_tabs:
            menu.add_command(label=tab_name, 
                             command=lambda name=tab_name, nb_ref=notebook_ref, fr_id=tab_frame_str, current_nb=current_notebook, current_fr=current_tab_frame: 
                                 self.set_and_get_source_tab_content(selected_source_tab_var, name, nb_ref, fr_id, current_nb, current_fr))
        
        current_tab_info['get_source_tab_button'].config(state=tk.NORMAL)
        current_tab_info['auto_update_checkbox'].config(state=tk.NORMAL) 

        self.set_and_get_source_tab_content(selected_source_tab_var, available_tabs[0][0], available_tabs[0][2], available_tabs[0][1], current_notebook, current_tab_frame)

    def _get_simple_tab_name(self, notebook_widget, tab_frame):
        """소스 드롭다운에서 사용할 단순하고 명확한 탭 이름을 생성합니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        side_name = current_tab_info['side_name']
        tab_suffix = current_tab_info['tab_index_suffix']
        tab_kind_map = {
            "normal": "일반",
            "filter": "필터",
            "replace": "치환",
            "line_capture": "캡쳐",
        }
        tab_kind_str = ""
        if current_tab_info['tab_source_var'].get() == "Cmdline":
            tab_kind_str = "Cmd"
        else:
            tab_kind_str = tab_kind_map.get(current_tab_info['type'], "일반")
        return f"{side_name}{tab_suffix}({tab_kind_str})"


    def set_and_get_source_tab_content(self, var, value, source_notebook_ref, source_frame_id_str, current_notebook, current_tab_frame):
        """StringVar를 설정하고 다른 탭에서 내용을 가져오는 헬퍼 함수입니다."""
        var.set(value)
        dependent_tab_id = (str(current_notebook), str(current_tab_frame))
        source_tab_id = (str(source_notebook_ref), source_frame_id_str)

        self.remove_dependent_tab(current_notebook, current_tab_frame)

        current_tab_info = self.tab_info_map[current_notebook][str(current_tab_frame)]
        if current_tab_info['auto_update_var'].get():
            if source_tab_id not in self.dependency_map:
                self.dependency_map[source_tab_id] = []
            if dependent_tab_id not in self.dependency_map[source_tab_id]:
                self.dependency_map[source_tab_id].append(dependent_tab_id)
            
            if source_notebook_ref in self.tab_info_map and source_frame_id_str in self.tab_info_map[source_notebook_ref]:
                source_tab_info = self.tab_info_map[source_notebook_ref][source_frame_id_str]
                current_tab_info['last_source_content_hash'] = hash(source_tab_info['current_display_content'])
            else:
                current_tab_info['last_source_content_hash'] = None 

        self.get_content_from_other_tab(current_notebook, current_tab_frame)

    def get_content_from_other_tab(self, current_notebook, current_tab_frame):
        """다른 탭에서 내용을 가져와 현재 탭의 소스 내용으로 설정합니다."""
        current_tab_info = self.tab_info_map[current_notebook][str(current_tab_frame)]
        selected_tab_name = current_tab_info['selected_source_tab'].get()
        
        source_content = b"" 
        source_tab_found = False
        source_nb_ref = None
        source_frame_id = None

        for nb in [self.left_notebook, self.right_notebook]:
            if nb in self.tab_info_map:
                for frame_id, info in self.tab_info_map[nb].items():
                    tab_frame = self.get_frame_from_id(nb, frame_id)
                    if self._get_simple_tab_name(nb, tab_frame) == selected_tab_name:
                        source_tab_info = info
                        source_content = source_tab_info['current_display_content']
                        source_tab_found = True
                        source_nb_ref = nb
                        source_frame_id = frame_id
                        break
                if source_tab_found:
                    break

        if source_tab_found:
            current_tab_info['source_content'] = source_content
            self.update_tab_display(current_notebook, current_tab_frame) 
            self.update_status_label(current_notebook, current_tab_frame) 
            
            if source_nb_ref and source_frame_id:
                source_tab_info_for_hash = self.tab_info_map[source_nb_ref][source_frame_id]
                current_tab_info['last_source_content_hash'] = hash(source_tab_info_for_hash['current_display_content'])
        else:
            self.display_result(current_tab_info['display_widget'], "소스 탭 내용을 가져올 수 없습니다.", state='disabled') 
            current_tab_info['source_content'] = b''
            current_tab_info['last_source_content_hash'] = None 
            self.update_status_label(current_notebook, current_tab_frame)

    def toggle_auto_update(self, notebook_widget, tab_frame):
        """자동 업데이트 체크 버튼의 상태 변경을 처리합니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        
        dependent_tab_id = (str(notebook_widget), str(tab_frame))

        if current_tab_info['auto_update_var'].get(): 
            selected_tab_name = current_tab_info['selected_source_tab'].get()
            source_nb_ref = None
            source_frame_id = None
            found_source = False 

            for nb in [self.left_notebook, self.right_notebook]:
                if nb in self.tab_info_map:
                    for frame_id, info in self.tab_info_map[nb].items():
                        tab_frame_candidate = self.get_frame_from_id(nb, frame_id)
                        if self._get_simple_tab_name(nb, tab_frame_candidate) == selected_tab_name and \
                           tab_frame_candidate != tab_frame:
                            source_nb_ref = nb
                            source_frame_id = frame_id
                            found_source = True
                            break
                if found_source:
                    break
            
            if found_source:
                source_tab_id = (str(source_nb_ref), source_frame_id)
                if source_tab_id not in self.dependency_map:
                    self.dependency_map[source_tab_id] = []
                if dependent_tab_id not in self.dependency_map[source_tab_id]:
                    self.dependency_map[source_tab_id].append(dependent_tab_id)
                
                source_tab_info = self.tab_info_map[source_nb_ref][source_frame_id]
                current_tab_info['last_source_content_hash'] = hash(source_tab_info['current_display_content'])
                self.get_content_from_other_tab(notebook_widget, tab_frame)
            else:
                current_tab_info['auto_update_var'].set(False) 
                self.update_status_label(notebook_widget, tab_frame, "오류: 소스 탭을 찾을 수 없습니다.")
        else: 
            self.remove_dependent_tab(notebook_widget, tab_frame)

    def remove_dependent_tab(self, current_notebook, current_tab_frame):
        """모든 소스 의존성 목록에서 탭을 제거합니다."""
        dependent_tab_tuple = (str(current_notebook), str(current_tab_frame))
        for source_tab_id, dependents in list(self.dependency_map.items()):
            if dependent_tab_tuple in dependents:
                dependents.remove(dependent_tab_tuple)
            if not dependents: 
                del self.dependency_map[source_tab_id]

    def check_for_auto_updates(self):
        """주기적으로 소스 탭 내용이 변경되었는지 확인하고 의존 탭을 업데이트합니다."""
        
        for source_nb_id_str, source_frame_id_str in list(self.dependency_map.keys()):
            source_nb = self.get_notebook_from_id_str(source_nb_id_str)
            source_frame = self.get_frame_from_id(source_nb, source_frame_id_str)

            if not source_frame or str(source_frame) not in self.tab_info_map[source_nb]:
                if (source_nb_id_str, source_frame_id_str) in self.dependency_map:
                    del self.dependency_map[(source_nb_id_str, source_frame_id_str)]
                continue

            source_tab_info = self.tab_info_map[source_nb][str(source_frame)]
            current_source_content = source_tab_info['current_display_content']
            current_source_hash = hash(current_source_content)

            dependent_tabs_to_update = []
            
            if (source_nb_id_str, source_frame_id_str) in self.dependency_map:
                for dep_nb_id_str, dep_frame_id_str in self.dependency_map[(source_nb_id_str, source_frame_id_str)]:
                    dep_nb = self.get_notebook_from_id_str(dep_nb_id_str)
                    dep_frame = self.get_frame_from_id(dep_nb, dep_frame_id_str)

                    if not dep_frame or str(dep_frame) not in self.tab_info_map[dep_nb]:
                        continue 
                    
                    dependent_tab_info = self.tab_info_map[dep_nb][str(dep_frame)]

                    if dependent_tab_info['auto_update_var'].get() and \
                       dependent_tab_info['last_source_content_hash'] != current_source_hash:
                        dependent_tabs_to_update.append((dep_nb, dep_frame))
                        dependent_tab_info['last_source_content_hash'] = current_source_hash
            
            for dep_nb, dep_frame in dependent_tabs_to_update:
                self.get_content_from_other_tab(dep_nb, dep_frame) 

        self.root.after(1000, self.check_for_auto_updates) 

    def get_notebook_from_id_str(self, nb_id_str):
        """문자열 ID로 노트북 위젯을 가져오는 헬퍼 함수입니다."""
        if str(self.left_notebook) == nb_id_str:
            return self.left_notebook
        elif str(self.right_notebook) == nb_id_str:
            return self.right_notebook
        return None

    def update_tab_display(self, notebook_widget, tab_frame):
        """
        현재 탭 유형 및 소스 내용에 따라 표시되는 내용을 업데이트합니다.
        """
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        
        display_state = 'disabled' 
        if current_tab_info['tab_source_var'].get() == "직접 텍스트 입력":
            display_state = 'normal'

        if current_tab_info['tab_source_var'].get() == "직접 텍스트 입력":
            self.display_result(current_tab_info['display_widget'], current_tab_info['source_content'].decode('utf-8', errors='replace'), state=display_state)
            current_tab_info['current_display_content'] = current_tab_info['source_content']
        elif current_tab_info['tab_source_var'].get() == "Cmdline":
            current_tab_info['display_widget'].config(state='disabled')
            self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
        elif current_tab_info['type'] == "filter":
            self.apply_filter(notebook_widget, tab_frame)
        elif current_tab_info['type'] == "replace":
            self.apply_regex(notebook_widget, tab_frame)
        elif current_tab_info['type'] == "line_capture":
            self.apply_line_capture(notebook_widget, tab_frame)
        else: 
            self.display_result(current_tab_info['display_widget'], current_tab_info['source_content'].decode('utf-8', errors='replace'), state='disabled')
            current_tab_info['current_display_content'] = current_tab_info['source_content']

    def update_source_content_on_key_release(self, notebook_widget, tab_frame):
        """'직접 텍스트 입력' 탭에서 사용자가 입력할 때 소스 내용을 업데이트합니다."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        if current_tab_info['tab_source_var'].get() == "직접 텍스트 입력":
            new_content_str = current_tab_info['display_widget'].get(1.0, tk.END).strip()
            new_content_bytes = new_content_str.encode('utf-8', errors='replace')
            current_tab_info['source_content'] = new_content_bytes
            current_tab_info['current_display_content'] = new_content_bytes
            if current_tab_info['type'] == "filter":
                self.apply_filter(notebook_widget, tab_frame)
            elif current_tab_info['type'] == "replace":
                self.apply_regex(notebook_widget, tab_frame)
            elif current_tab_info['type'] == "line_capture":
                self.apply_line_capture(notebook_widget, tab_frame)

    def display_result(self, text_widget, content_str, state='normal'):
        """ScrolledText 위젯의 내용을 업데이트하는 헬퍼 함수입니다."""
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        text_widget.insert(tk.END, content_str)
        text_widget.config(state=state)

    def apply_filter(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        source_content = current_tab_info['source_content'] 
        include_regex_bytes = current_tab_info['include_regex'].get().encode('utf-8')
        exclude_regex_bytes = current_tab_info['exclude_regex'].get().encode('utf-8')
        
        lines = source_content.split(b'\n') 
        filtered_lines = []
        
        try:
            include_pattern = re.compile(include_regex_bytes) if include_regex_bytes else None
            exclude_pattern = re.compile(exclude_regex_bytes) if exclude_regex_bytes else None

            for line in lines:
                should_include = True
                if include_pattern and not include_pattern.search(line):
                    should_include = False
                if exclude_pattern and exclude_pattern.search(line):
                    should_include = False
                
                if should_include:
                    filtered_lines.append(line)
            
            filtered_content = b"\n".join(filtered_lines) 
            self.display_result(current_tab_info['display_widget'], filtered_content.decode('utf-8', errors='replace'), state='disabled')
            current_tab_info['current_display_content'] = filtered_content
            self.update_status_label(notebook_widget, tab_frame, "필터 적용 완료")
        except re.error as e:
            error_msg_str = f"정규식 오류: {e}" 
            error_msg_bytes = error_msg_str.encode('utf-8') 
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled') 
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"필터 적용 오류: {e}")

    def apply_regex(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        source_content = current_tab_info['source_content'] 
        regex_pattern_bytes = current_tab_info['regex_pattern'].get().encode('utf-8')
        replace_string_bytes = current_tab_info['replace_string'].get().encode('utf-8')

        if not regex_pattern_bytes:
            self.display_result(current_tab_info['display_widget'], "정규식을 입력하세요.", state='disabled') 
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "치환 적용 오류: 정규식 없음")
            return

        try:
            replaced_content = re.sub(regex_pattern_bytes, replace_string_bytes, source_content)
            self.display_result(current_tab_info['display_widget'], replaced_content.decode('utf-8', errors='replace'), state='disabled')
            current_tab_info['current_display_content'] = replaced_content
            self.update_status_label(notebook_widget, tab_frame, "치환 적용 완료")
        except re.error as e:
            error_msg_str = f"정규식 오류: {e}" 
            error_msg_bytes = error_msg_str.encode('utf-8') 
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled') 
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"치환 적용 오류: {e}")

    def apply_line_capture(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        source_content = current_tab_info['source_content'] 
        start_regex_bytes = current_tab_info['start_regex'].get().encode('utf-8')
        end_regex_bytes = current_tab_info['end_regex'].get().encode('utf-8')
        
        lines = source_content.split(b'\n')
        captured_lines = []
        capture_mode = False

        if not start_regex_bytes:
            self.display_result(current_tab_info['display_widget'], "START 정규식을 입력하세요.", state='disabled') 
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "라인 캡쳐 오류: START 정규식 없음")
            return

        try:
            start_pattern = re.compile(start_regex_bytes)
            end_pattern = re.compile(end_regex_bytes) if end_regex_bytes else None

            for line in lines:
                if not capture_mode and start_pattern.search(line):
                    capture_mode = True
                    captured_lines.append(line)
                elif capture_mode:
                    captured_lines.append(line)
                    if end_pattern and end_pattern.search(line):
                        capture_mode = False
            
            captured_content = b"\n".join(captured_lines) 
            self.display_result(current_tab_info['display_widget'], captured_content.decode('utf-8', errors='replace'), state='disabled')
            current_tab_info['current_display_content'] = captured_content
            self.update_status_label(notebook_widget, tab_frame, "라인 캡쳐 적용 완료")
        except re.error as e:
            error_msg_str = f"정규식 오류: {e}" 
            error_msg_bytes = error_msg_str.encode('utf-8') 
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled') 
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"라인 캡쳐 오류: {e}")
            
    def execute_command(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        command = current_tab_info['cmd_input_var'].get() 
        file_val = current_tab_info['cmd_f_var'].get() 
        url_val = current_tab_info['cmd_u_var'].get()   
        current_cwd = current_tab_info['current_cwd'] 
        
        if not command.strip():
            self.display_result(current_tab_info['display_widget'], "실행할 명령을 입력하세요.", state='disabled') 
            self.update_status_label(notebook_widget, tab_frame, "명령 실행 오류: 명령 없음")
            return

        processed_command = command.replace("%f", file_val).replace("%u", url_val)

        if processed_command.lower().strip().startswith("cd "):
            new_path = processed_command.strip()[3:].strip()
            if platform.system() == "Windows":
                if re.match(r'^[a-zA-Z]:\\', new_path) or new_path.startswith('\\'):
                    abs_path = os.path.normpath(new_path)
                else:
                    abs_path = os.path.normpath(os.path.join(current_cwd, new_path))
            else: 
                if new_path.startswith('/'):
                    abs_path = os.path.normpath(new_path)
                else:
                    abs_path = os.path.normpath(os.path.join(current_cwd, new_path))
            
            try:
                if os.path.isdir(abs_path):
                    current_tab_info['current_cwd'] = abs_path
                    output_str = f"디렉토리 변경: {abs_path}\n"
                    output_bytes = output_str.encode('utf-8', errors='replace')
                    current_tab_info['current_display_content'] += output_bytes
                    self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
                    self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']}")
                else:
                    output_str = f"오류: '{new_path}' 디렉토리를 찾을 수 없습니다.\n"
                    output_bytes = output_str.encode('utf-8', errors='replace')
                    current_tab_info['current_display_content'] += output_bytes
                    self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
                    self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (CD 오류)")
            except Exception as e:
                output_str = f"CD 명령 실행 오류: {e}\n"
                output_bytes = output_str.encode('utf-8', errors='replace')
                current_tab_info['current_display_content'] += output_bytes
                self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
                self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (CD 오류)")
            return

        try:
            process = subprocess.Popen(processed_command,
                                       shell=True, 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE, 
                                       cwd=current_cwd)
            stdout_bytes, stderr_bytes = process.communicate() 

            output_bytes = f"$ {processed_command}\n".encode('utf-8', errors='replace') 
            output_bytes += stdout_bytes
            if stderr_bytes:
                output_bytes += f"오류: ".encode('utf-8') + stderr_bytes
            
            current_tab_info['current_display_content'] += output_bytes
            self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
            self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (명령 실행 완료)")

        except Exception as e:
            error_output_str = f"$ {processed_command}\n오류: {e}\n"
            error_output_bytes = error_output_str.encode('utf-8', errors='replace')
            current_tab_info['current_display_content'] += error_output_bytes
            self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
            self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (명령 실행 오류)")

    def update_status_label(self, notebook_widget, tab_frame, custom_message=None):
        """
        주어진 탭의 상태 라벨을 상황에 맞는 정보로 업데이트합니다.
        custom_message가 있으면 해당 메시지가 우선적으로 표시됩니다.
        """
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        status_label = current_tab_info['status_label']
        
        status_text = ""
        if custom_message:
            status_text = custom_message
        else:
            tab_source_type = current_tab_info['tab_source_var'].get()
            tab_logic_type = current_tab_info['type']
            
            if tab_source_type == "파일에서 로드":
                status_text = "파일에서 로드됨"
            elif tab_source_type == "직접 텍스트 입력":
                status_text = "직접 텍스트 입력 중"
            elif tab_source_type == "다른 탭에서 가져오기":
                status_text = f"'{current_tab_info['selected_source_tab'].get()}' 탭에서 가져옴"
            elif tab_source_type == "Cmdline":
                status_text = f"CWD: {current_tab_info['current_cwd']}" 
            
            if tab_source_type != "Cmdline": 
                if tab_logic_type == "filter":
                    status_text += " (필터 적용 대기 중)" if not current_tab_info['current_display_content'].strip() else " (필터 적용됨)"
                elif tab_logic_type == "replace":
                    status_text += " (치환 적용 대기 중)" if not current_tab_info['current_display_content'].strip() else " (치환 적용됨)"
                elif tab_logic_type == "line_capture":
                    status_text += " (라인 캡쳐 적용 대기 중)" if not current_tab_info['current_display_content'].strip() else " (라인 캡쳐 적용됨)"
                else: 
                    if not current_tab_info['source_content'].strip() and tab_source_type != "직접 텍스트 입력":
                         status_text += " (내용 없음)"

        status_label.config(text=status_text)

    def close_tab_from_button(self, notebook_widget, tab_frame):
        """'탭 닫기' 버튼 클릭 시 탭을 제거합니다."""
        tab_id = tab_frame.winfo_id()
        for i, frame_id in enumerate(notebook_widget.tabs()):
            if notebook_widget.nametowidget(frame_id) == tab_frame:
                self.remove_dependent_tab(notebook_widget, tab_frame)
                del self.tab_info_map[notebook_widget][str(tab_frame)]
                notebook_widget.forget(i)
                break
        
        if not notebook_widget.tabs():
            side_name = "좌" if notebook_widget == self.left_notebook else "우"
            self.add_new_tab(notebook_widget, side_name)


if __name__ == "__main__":
    root = tk.Tk()
    app = FileViewerApp(root)
    root.mainloop()
