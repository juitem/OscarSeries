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

        # Set default font based on OS
        self.default_font = self._get_default_font()

        # --- Control Frame: New Tab Buttons ---
        self.control_frame = tk.Frame(self.root)
        self.control_frame.pack(pady=10, fill=tk.X, padx=2)

        # Left New Tab Button
        self.left_new_tab_button = tk.Button(self.control_frame, text="New Tab (L)",
                                             command=lambda: self.add_new_tab(self.left_notebook, "L"))
        self.left_new_tab_button.pack(side=tk.LEFT, padx=(0, 5), anchor="w")

        # Right New Tab Button
        self.right_new_tab_button = tk.Button(self.control_frame, text="New Tab (R)",
                                              command=lambda: self.add_new_tab(self.right_notebook, "R"))
        self.right_new_tab_button.pack(side=tk.RIGHT, padx=(5, 0), anchor="e")

        # --- Main Content Frame: Tab View ---
        self.tab_view_frame = tk.Frame(self.root)
        self.tab_view_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=2)

        # Left Notebook (Tab Control)
        self.left_notebook = ttk.Notebook(self.tab_view_frame)
        self.left_notebook.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 5))

        # Right Notebook (Tab Control)
        self.right_notebook = ttk.Notebook(self.tab_view_frame)
        self.right_notebook.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH, padx=(5, 0))

        self.tab_info_map = {}
        self.tab_index_counter = {'left': 1, 'right': 1} 
        
        # --- Dependency map for auto-updates ---
        # {source_tab_id: [dependent_tab_id1, dependent_tab_id2, ...]}
        self.dependency_map = {} 
        self.root.after(1000, self.check_for_auto_updates) # Start periodic check every 1 second

        # Create initial tabs
        self.add_new_tab(self.left_notebook, "L")
        self.add_new_tab(self.right_notebook, "R")

    def _get_default_font(self):
        """Returns a default font name based on the operating system."""
        system = platform.system()
        if system == "Windows":
            return "Arial"
        elif system == "Darwin": # macOS
            return "Helvetica"
        elif system == "Linux": # Ubuntu, etc.
            return "DejaVu Sans" # Or "Liberation Sans"
        else:
            return "TkDefaultFont" # For other OS, use Tkinter's default font

    def add_new_tab(self, notebook_widget, side_name):
        new_frame = ttk.Frame(notebook_widget)
        
        side_key = "left" if notebook_widget == self.left_notebook else "right"
        
        tab_suffix = self.tab_index_counter[side_key]
        self.tab_index_counter[side_key] += 1

        initial_tab_type = "normal"
        
        notebook_widget.add(new_frame, text="New Tab...") # Temporary tab name
        
        if notebook_widget not in self.tab_info_map:
            self.tab_info_map[notebook_widget] = {}
        
        include_regex_var = tk.StringVar()
        exclude_regex_var = tk.StringVar()
        regex_var = tk.StringVar()
        replace_var = tk.StringVar()
        start_regex_var = tk.StringVar()
        end_regex_var = tk.StringVar()
        source_tab_var = tk.StringVar()
        
        # Cmdline related variables
        command_input_var = tk.StringVar()
        cmd_f_var = tk.StringVar() 
        cmd_u_var = tk.StringVar() 
        current_working_directory = os.getcwd() 

        # Auto-update variable (default True)
        auto_update_var = tk.BooleanVar(value=True) 

        # --- New Compare Tab related variables ---
        comparison_source_tab_var = tk.StringVar()
        # Decimal RegEx (default)
        decimal_regex_var = tk.StringVar(value=r'\b\d+\b')
        # Hex RegEx (default)
        hex_regex_var = tk.StringVar(value=r'\b0x[0-9a-fA-F]+\b')
        
        # Decimal/Hex enable checkboxes variables
        enable_decimal_var = tk.BooleanVar(value=True)
        enable_hex_var = tk.BooleanVar(value=True)


        tab_info = {
            'type': initial_tab_type, 
            'source_content': b'', # Store as bytes
            'current_display_content': b'', # Store as bytes
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
            
            # Cmdline specific info
            'cmd_input_var': command_input_var,
            'cmd_f_var': cmd_f_var,
            'cmd_u_var': cmd_u_var,
            'current_cwd': current_working_directory,
            'cmd_input_entry': None, 
            'cmd_run_button': None, 
            'cmd_ui_frame': None, 
            'cmd_f_entry': None, 
            'cmd_u_entry': None, 
            
            # Auto-update info
            'auto_update_var': auto_update_var,
            'auto_update_checkbox': None, 
            'last_source_content_hash': None, 
            
            # Reference to tab type change menu
            'tab_type_menu': None,

            # --- New Compare Tab specific info ---
            'comparison_source_tab_var': comparison_source_tab_var,
            'comparison_source_selection_frame': None,
            'comparison_source_menu': None,
            'decimal_regex_var': decimal_regex_var, # Decimal RegEx variable
            'hex_regex_var': hex_regex_var,         # Hex RegEx variable
            'enable_decimal_var': enable_decimal_var, # Enable decimal variable
            'enable_hex_var': enable_hex_var,         # Enable hex variable
            'decimal_regex_entry': None,
            'hex_regex_entry': None,
            'enable_decimal_checkbox': None,
            'enable_hex_checkbox': None,
            'apply_comparison_button': None,
            'comparison_source_tab_id': None, # Tuple of (Notebook_ID, Frame_ID) for comparison target tab
            'last_comparison_source_content_hash': None, # For detecting changes in comparison target tab content
        }
        self.tab_info_map[notebook_widget][str(new_frame)] = tab_info

        # --- Top control frame inside the tab ---
        control_sub_frame = tk.Frame(new_frame)
        control_sub_frame.pack(fill=tk.X, padx=5, pady=2)

        # Source selection menu
        tab_info['tab_source_var'].set("Direct Text Input")
        tab_source_options = ["Load from File", "Direct Text Input", "Get from Other Tab", "Cmdline"]
        tab_source_menu = tk.OptionMenu(control_sub_frame, tab_info['tab_source_var'], *tab_source_options,
                                        command=lambda opt, f=new_frame, n=notebook_widget: self.on_tab_source_change(n, f, opt))
        tab_source_menu.pack(side=tk.LEFT, padx=(0, 10))

        # Source tab selection dropdown (initially hidden)
        tab_info['source_tab_selection_frame'] = tk.Frame(control_sub_frame)
        tab_info['source_tab_selection_frame'].pack(side=tk.LEFT, padx=(0, 5))
        
        tab_info['source_tab_menu'] = tk.OptionMenu(tab_info['source_tab_selection_frame'], tab_info['selected_source_tab'], "")
        tab_info['source_tab_menu'].pack(side=tk.LEFT)
        tab_info['source_tab_selection_frame'].pack_forget()

        # 'Get' button
        tab_info['get_source_tab_button'] = tk.Button(tab_info['source_tab_selection_frame'], text="Get",
                                                command=lambda n=notebook_widget, f=new_frame: self.get_content_from_other_tab(n, f))
        tab_info['get_source_tab_button'].pack(side=tk.LEFT, padx=(5,0))
        tab_info['source_tab_selection_frame'].pack_forget()

        # Auto-update checkbox
        tab_info['auto_update_checkbox'] = tk.Checkbutton(
            tab_info['source_tab_selection_frame'],
            text="Auto Update",
            variable=tab_info['auto_update_var'],
            command=lambda n=notebook_widget, f=new_frame: self.toggle_auto_update(n, f)
        )
        tab_info['auto_update_checkbox'].pack(side=tk.LEFT, padx=(5,0))
        tab_info['auto_update_checkbox'].pack_forget()

        # Tab type change menu
        tab_info['tab_type_var'] = tk.StringVar(new_frame)
        tab_info['tab_type_var'].set(self.get_display_tab_type(initial_tab_type)) 
        
        # Add 'Convert to Compare Tab' option
        tab_type_options = ["-> Normal Tab", "-> Filter Tab", "-> Replace Tab", "-> Line Capture Tab", "-> Compare Tab"]
        tab_type_menu = tk.OptionMenu(control_sub_frame, tab_info['tab_type_var'], *tab_type_options,
                                      command=lambda opt, f=new_frame, n=notebook_widget: self.change_tab_type(n, f, opt))
        tab_type_menu.pack(side=tk.LEFT, padx=(10, 0))
        tab_info['tab_type_menu'] = tab_type_menu 

        # 탭 닫기 버튼
        close_tab_button = tk.Button(control_sub_frame, text="x", 
                                     command=lambda nb=notebook_widget, frame=new_frame: self.close_tab_from_button(nb, frame))
        close_tab_button.pack(side=tk.RIGHT, padx=(10, 0))

        # --- Dynamic UI elements frame (RegEx/Replace/Line Capture/Compare fields) ---
        tab_info['dynamic_ui_elements_frame'] = tk.Frame(new_frame)
        tab_info['dynamic_ui_elements_frame'].pack(fill=tk.X, padx=5, pady=5)
        
        # Create all possible dynamic UI elements, but hide them initially
        self.create_dynamic_ui_elements(tab_info)
        
        # Text widget (main content display area)
        # Apply font
        text_widget = scrolledtext.ScrolledText(new_frame, wrap=tk.WORD, font=(self.default_font, 10)) 
        text_widget.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        text_widget.config(state='normal') 
        tab_info['display_widget'] = text_widget
        
        # Update source content on key release for 'Direct Text Input' tab
        text_widget.bind("<KeyRelease>", lambda e, n=notebook_widget, f=new_frame: self.update_source_content_on_key_release(n, f))

        # --- Status Label Frame (moved to bottom) ---
        status_frame = tk.Frame(new_frame)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        
        tab_status_label = tk.Label(status_frame, text="", anchor="w") 
        tab_status_label.pack(side=tk.LEFT, expand=True, fill=tk.X)
        tab_info['status_label'] = tab_status_label

        notebook_widget.select(new_frame)
        
        tab_info['current_display_content'] = b''
        tab_info['source_content'] = b'' 

        # Initial status update
        self.update_tab_display(notebook_widget, new_frame)
        self.update_status_label(notebook_widget, new_frame) 
        self._update_tab_name(notebook_widget, new_frame) 

    def _update_tab_name(self, notebook_widget, tab_frame):
        """Updates the display name of the tab based on its current state."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        
        side_name = current_tab_info['side_name']
        tab_suffix = current_tab_info['tab_index_suffix']
        tab_source_type = current_tab_info['tab_source_var'].get()
        tab_logic_type = current_tab_info['type']
        
        tab_kind_map = {
            "normal": "Normal",
            "filter": "Filter",
            "replace": "Replace",
            "line_capture": "Line Capture",
            "comparison": "Compare", # 'Compare' tab type added
        }
        tab_kind_str = ""
        if tab_source_type == "Cmdline":
            tab_kind_str = "Cmd"
        else:
            tab_kind_str = tab_kind_map.get(tab_logic_type, "Normal")
        
        is_source_tab = (tab_source_type == "Direct Text Input" or tab_source_type == "Load from File")
        
        parts = []
        if is_source_tab:
            parts.append("Source")
        parts.append(tab_kind_str)
        
        name_details = ", ".join(parts)
        
        new_tab_name = f"{side_name}{tab_suffix}({name_details})"
        
        current_tab_index = notebook_widget.index(tab_frame)
        notebook_widget.tab(current_tab_index, text=new_tab_name)

    def create_dynamic_ui_elements(self, tab_info):
        """Creates all dynamic UI elements and hides them initially."""
        dynamic_frame = tab_info['dynamic_ui_elements_frame']
        
        # --- Filter Tab UI elements ---
        filter_elements = {}
        filter_frame = tk.Frame(dynamic_frame) 
        lbl1 = tk.Label(filter_frame, text="Include RegEx:")
        entry1 = tk.Entry(filter_frame, textvariable=tab_info['include_regex'], width=30)
        entry1.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_filter(n, self.get_frame_from_id(n, f)))
        lbl2 = tk.Label(filter_frame, text="Exclude RegEx:")
        entry2 = tk.Entry(filter_frame, textvariable=tab_info['exclude_regex'], width=30)
        entry2.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_filter(n, self.get_frame_from_id(n, f)))
        btn = tk.Button(filter_frame, text="Apply", 
                         command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_filter(n, self.get_frame_from_id(n, f)))
        filter_elements['frame'] = filter_frame
        filter_elements['widgets'] = [lbl1, entry1, lbl2, entry2, btn]
        tab_info['dynamic_ui_elements']['filter'] = filter_elements

        # --- Replace Tab UI elements ---
        replace_elements = {}
        replace_frame = tk.Frame(dynamic_frame) 
        lbl1 = tk.Label(replace_frame, text="RegEx:")
        entry1 = tk.Entry(replace_frame, textvariable=tab_info['regex_pattern'], width=30)
        entry1.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_regex(n, self.get_frame_from_id(n, f)))
        lbl2 = tk.Label(replace_frame, text="Replace String:")
        entry2 = tk.Entry(replace_frame, textvariable=tab_info['replace_string'], width=30)
        entry2.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_regex(n, self.get_frame_from_id(n, f)))
        btn = tk.Button(replace_frame, text="Apply",
                         command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_regex(n, self.get_frame_from_id(n, f)))
        replace_elements['frame'] = replace_frame
        replace_elements['widgets'] = [lbl1, entry1, lbl2, entry2, btn]
        tab_info['dynamic_ui_elements']['replace'] = replace_elements

        # --- Line Capture Tab UI elements ---
        line_capture_elements = {}
        line_capture_frame = tk.Frame(dynamic_frame) 
        lbl1 = tk.Label(line_capture_frame, text="START RegEx:")
        entry1 = tk.Entry(line_capture_frame, textvariable=tab_info['start_regex'], width=25)
        entry1.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_line_capture(n, self.get_frame_from_id(n, f)))
        lbl2 = tk.Label(line_capture_frame, text="END RegEx:")
        entry2 = tk.Entry(line_capture_frame, textvariable=tab_info['end_regex'], width=25)
        entry2.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_line_capture(n, self.get_frame_from_id(n, f)))
        btn = tk.Button(line_capture_frame, text="Apply",
                         command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_line_capture(n, self.get_frame_from_id(n, f)))
        line_capture_elements['frame'] = line_capture_frame
        line_capture_elements['widgets'] = [lbl1, entry1, lbl2, entry2, btn]
        tab_info['dynamic_ui_elements']['line_capture'] = line_capture_elements

        # --- Cmdline Tab UI elements ---
        cmdline_elements = {}
        cmdline_frame = tk.Frame(dynamic_frame) 
        cmd_input_frame = tk.Frame(cmdline_frame)
        cmd_input_frame.pack(fill=tk.X, pady=(0, 2))
        cmd_label = tk.Label(cmd_input_frame, text="Cmd:")
        cmd_label.pack(side=tk.LEFT)
        cmd_entry = tk.Entry(cmd_input_frame, textvariable=tab_info['cmd_input_var'], width=60)
        cmd_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        cmd_entry.bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.execute_command(n, self.get_frame_from_id(n, f)))
        cmd_button = tk.Button(cmd_input_frame, text="Run",
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

        # --- Compare Tab UI elements (newly added) ---
        comparison_elements = {}
        comparison_frame = tk.Frame(dynamic_frame)

        # Comparison target source selection dropdown
        comp_source_selection_frame = tk.Frame(comparison_frame)
        comp_source_selection_frame.pack(fill=tk.X, pady=(0, 2))
        
        comp_source_label = tk.Label(comp_source_selection_frame, text="Compare Source:")
        comp_source_label.pack(side=tk.LEFT)
        
        tab_info['comparison_source_menu'] = tk.OptionMenu(comp_source_selection_frame, tab_info['comparison_source_tab_var'], "")
        tab_info['comparison_source_menu'].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
        tab_info['comparison_source_selection_frame'] = comp_source_selection_frame

        # Decimal RegEx input field and checkbox
        decimal_regex_frame = tk.Frame(comparison_frame)
        decimal_regex_frame.pack(fill=tk.X, pady=(0, 2))
        
        decimal_regex_label = tk.Label(decimal_regex_frame, text="Decimal RegEx:")
        decimal_regex_label.pack(side=tk.LEFT)
        
        tab_info['decimal_regex_entry'] = tk.Entry(decimal_regex_frame, textvariable=tab_info['decimal_regex_var'], width=40)
        tab_info['decimal_regex_entry'].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
        tab_info['decimal_regex_entry'].bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_comparison(n, self.get_frame_from_id(n, f)))

        tab_info['enable_decimal_checkbox'] = tk.Checkbutton(
            decimal_regex_frame,
            text="Enable",
            variable=tab_info['enable_decimal_var'],
            command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_comparison(n, self.get_frame_from_id(n, f))
        )
        tab_info['enable_decimal_checkbox'].pack(side=tk.LEFT, padx=(5,0))


        # Hex RegEx input field and checkbox
        hex_regex_frame = tk.Frame(comparison_frame)
        hex_regex_frame.pack(fill=tk.X, pady=(0, 2))
        
        hex_regex_label = tk.Label(hex_regex_frame, text="Hex RegEx:")
        hex_regex_label.pack(side=tk.LEFT)
        
        tab_info['hex_regex_entry'] = tk.Entry(hex_regex_frame, textvariable=tab_info['hex_regex_var'], width=40)
        tab_info['hex_regex_entry'].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
        tab_info['hex_regex_entry'].bind("<Return>", lambda e, n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_comparison(n, self.get_frame_from_id(n, f)))

        tab_info['enable_hex_checkbox'] = tk.Checkbutton(
            hex_regex_frame,
            text="Enable",
            variable=tab_info['enable_hex_var'],
            command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_comparison(n, self.get_frame_from_id(n, f))
        )
        tab_info['enable_hex_checkbox'].pack(side=tk.LEFT, padx=(5,0))

        # Apply button (for Compare tab only)
        tab_info['apply_comparison_button'] = tk.Button(comparison_frame, text="Apply Compare",
                                                        command=lambda n=tab_info['parent_notebook'], f=tab_info['tab_content_frame_id']: self.apply_comparison(n, self.get_frame_from_id(n, f)))
        tab_info['apply_comparison_button'].pack(pady=(5,0))

        comparison_elements['frame'] = comparison_frame
        comparison_elements['widgets'] = [
            comp_source_selection_frame, 
            decimal_regex_frame, 
            hex_regex_frame, 
            tab_info['apply_comparison_button']
        ]
        tab_info['dynamic_ui_elements']['comparison'] = comparison_elements


    def get_frame_from_id(self, notebook_widget, frame_id_str):
        """Helper function to get a frame widget by its string ID."""
        for tab_id in notebook_widget.tabs():
            tab_frame = notebook_widget.nametowidget(tab_id)
            if str(tab_frame) == frame_id_str:
                return tab_frame
        return None 

    def hide_all_dynamic_ui(self, tab_info):
        """Hides all dynamic UI elements for a given tab."""
        for tab_type, elements in tab_info['dynamic_ui_elements'].items():
            if 'frame' in elements: 
                elements['frame'].pack_forget() 
        if tab_info['cmd_ui_frame']:
            tab_info['cmd_ui_frame'].pack_forget()
        if tab_info['auto_update_checkbox']:
            tab_info['auto_update_checkbox'].pack_forget()

    def show_tab_type_ui(self, notebook_widget, tab_frame, tab_type):
        """Displays the dynamic UI elements corresponding to the given tab_type."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        self.hide_all_dynamic_ui(current_tab_info) 

        # If source type is 'Cmdline', display Cmdline specific UI.
        if current_tab_info['tab_source_var'].get() == "Cmdline":
            if current_tab_info['cmd_ui_frame']:
                current_tab_info['cmd_ui_frame'].pack(fill=tk.X, padx=5, pady=5)
            return
        
        # 소스가 '다른 탭에서 가져오기'인 경우, 자동 업데이트 체크 버튼을 표시합니다.
        if current_tab_info['tab_source_var'].get() == "다른 탭에서 가져오기":
            if current_tab_info['auto_update_checkbox']:
                current_tab_info['auto_update_checkbox'].pack(side=tk.LEFT, padx=(5,0))

        # Display UI based on tab type.
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
                elif tab_type == "comparison": # Compare tab UI layout
                    # Compare Source selection dropdown
                    current_tab_info['comparison_source_selection_frame'].pack(fill=tk.X, pady=(0, 2))
                    # Decimal RegEx
                    current_tab_info['decimal_regex_entry'].master.pack(fill=tk.X, pady=(0, 2)) # master is the frame
                    current_tab_info['decimal_regex_entry'].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
                    current_tab_info['enable_decimal_checkbox'].pack(side=tk.LEFT, padx=(5,0))
                    # Hex RegEx
                    current_tab_info['hex_regex_entry'].master.pack(fill=tk.X, pady=(0, 2)) # master is the frame
                    current_tab_info['hex_regex_entry'].pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
                    current_tab_info['enable_hex_checkbox'].pack(side=tk.LEFT, padx=(5,0))
                    # Apply button
                    current_tab_info['apply_comparison_button'].pack(pady=(5,0))
                    self.populate_comparison_source_dropdown(notebook_widget, tab_frame)


    def get_actual_tab_type(self, display_text):
        """Converts the display text from OptionMenu to internal tab type string."""
        if "Normal Tab" in display_text:
            return "normal"
        elif "Filter Tab" in display_text:
            return "filter"
        elif "Replace Tab" in display_text:
            return "replace"
        elif "Line Capture Tab" in display_text:
            return "line_capture"
        elif "Compare Tab" in display_text: # 'Compare' tab type added
            return "comparison"
        return "normal" 

    def get_display_tab_type(self, actual_type):
        """Converts the internal tab type string to display text for OptionMenu."""
        if actual_type == "normal":
            return "Convert to Normal Tab"
        elif actual_type == "filter":
            return "Convert to Filter Tab"
        elif actual_type == "replace":
            return "Convert to Replace Tab"
        elif actual_type == "line_capture":
            return "Convert to Line Capture Tab"
        elif actual_type == "comparison": # 'Compare' tab type added
            return "Convert to Compare Tab"
        return "Convert to Normal Tab" 

    def change_tab_type(self, notebook_widget, tab_frame, selected_option_text):
        """Changes the type of the current tab and updates the UI."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        new_tab_type = self.get_actual_tab_type(selected_option_text)
        current_tab_info['type'] = new_tab_type 
        current_tab_info['tab_type_var'].set(selected_option_text)

        self.show_tab_type_ui(notebook_widget, tab_frame, new_tab_type)
        self.update_tab_display(notebook_widget, tab_frame)
        self.update_status_label(notebook_widget, tab_frame) 
        self._update_tab_name(notebook_widget, tab_frame) 

    def on_tab_source_change(self, notebook_widget, tab_frame, selected_option):
        """Called when the tab source selection menu changes."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        text_widget = current_tab_info['display_widget']
        source_tab_selection_frame = current_tab_info['source_tab_selection_frame']
        
        # First, hide all source-related UI elements.
        source_tab_selection_frame.pack_forget()
        if current_tab_info['cmd_ui_frame']:
            current_tab_info['cmd_ui_frame'].pack_forget()
        if current_tab_info['auto_update_checkbox']:
            current_tab_info['auto_update_checkbox'].pack_forget()

        text_widget.config(state='disabled')
        
        if current_tab_info['tab_source_var'].get() == "Direct Text Input":
            current_tab_info['current_display_content'] = text_widget.get(1.0, tk.END).strip().encode('utf-8')
        else:
            current_tab_info['current_display_content'] = b'' 

        if selected_option != "Cmdline":
             current_tab_info['source_content'] = b''

        # Remove the current tab from the dependency list of the previous source.
        self.remove_dependent_tab(current_notebook=notebook_widget, current_tab_frame=tab_frame)

        # Control the enabled state of the tab type change menu based on source type.
        if selected_option == "Cmdline":
            current_tab_info['tab_type_menu'].config(state=tk.DISABLED)
        else:
            current_tab_info['tab_type_menu'].config(state=tk.NORMAL)

        if selected_option == "Load from File":
            file_path = filedialog.askopenfilename(
                title="Select File",
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
                    content_str = f"File read error: {e}"
                    current_tab_info['source_content'] = b'' 
                    self.display_result(text_widget, content_str, state='disabled')
                    print(f"Error reading {file_path}: {e}")
            else:
                current_tab_info['tab_source_var'].set("Direct Text Input") 
                current_tab_info['tab_type_menu'].config(state=tk.NORMAL) 
                current_tab_info['source_content'] = current_tab_info['current_display_content'] 
                self.update_tab_display(notebook_widget, tab_frame) 

        elif selected_option == "Direct Text Input":
            text_widget.config(state='normal') 
            current_tab_info['source_content'] = current_tab_info['current_display_content'] 
            self.update_tab_display(notebook_widget, tab_frame)

        elif selected_option == "Get from Other Tab":
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
        """Populates the source tab selection dropdown menu."""
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
            selected_source_tab_var.set("No Tabs Available")
            menu.add_command(label="No Tabs Available", state=tk.DISABLED)
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

    def populate_comparison_source_dropdown(self, current_notebook, current_tab_frame):
        """Populates the comparison source selection dropdown menu."""
        current_tab_info = self.tab_info_map[current_notebook][str(current_tab_frame)]
        comparison_source_tab_var = current_tab_info['comparison_source_tab_var']
        comparison_source_menu = current_tab_info['comparison_source_menu']

        menu = comparison_source_menu['menu']
        menu.delete(0, 'end') # Clear existing options

        available_tabs = []
        # Get tabs from current notebook
        for tab_id in current_notebook.tabs():
            tab_frame = current_notebook.nametowidget(tab_id)
            # Current tab cannot be a comparison target.
            if str(tab_frame) in self.tab_info_map[current_notebook] and tab_frame != current_tab_frame:
                tab_name = self._get_simple_tab_name(current_notebook, tab_frame)
                available_tabs.append((tab_name, str(tab_frame), current_notebook))

        # Get tabs from other notebook
        other_notebook = self.left_notebook if current_notebook == self.right_notebook else self.right_notebook
        for tab_id in other_notebook.tabs():
            tab_frame = other_notebook.nametowidget(tab_id)
            if str(tab_frame) in self.tab_info_map[other_notebook]:
                tab_name = self._get_simple_tab_name(other_notebook, tab_frame)
                available_tabs.append((tab_name, str(tab_frame), other_notebook))
        
        if not available_tabs:
            comparison_source_tab_var.set("No Tabs Available")
            menu.add_command(label="No Tabs Available", state=tk.DISABLED)
            current_tab_info['apply_comparison_button'].config(state=tk.DISABLED)
            return

        # Set default selected tab
        comparison_source_tab_var.set(available_tabs[0][0]) 
        
        # Populate menu and set command to fetch content
        for tab_name, tab_frame_str, notebook_ref in available_tabs:
            menu.add_command(label=tab_name, 
                             command=lambda name=tab_name, nb_ref=notebook_ref, fr_id=tab_frame_str, current_nb=current_notebook, current_fr=current_tab_frame: 
                                 self.set_and_get_comparison_source_content(comparison_source_tab_var, name, nb_ref, fr_id, current_nb, current_fr))
        
        current_tab_info['apply_comparison_button'].config(state=tk.NORMAL)

        # Apply comparison immediately with the first tab's content after populating the dropdown
        self.set_and_get_comparison_source_content(comparison_source_tab_var, available_tabs[0][0], available_tabs[0][2], available_tabs[0][1], current_notebook, current_tab_frame)


    def _get_simple_tab_name(self, notebook_widget, tab_frame):
        """Generates a simple and clear tab name for use in source dropdowns."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        side_name = current_tab_info['side_name']
        tab_suffix = current_tab_info['tab_index_suffix']
        tab_kind_map = {
            "normal": "Normal",
            "filter": "Filter",
            "replace": "Replace",
            "line_capture": "Line Capture",
            "comparison": "Compare", # 'Compare' tab type added
        }
        tab_kind_str = ""
        if current_tab_info['tab_source_var'].get() == "Cmdline":
            tab_kind_str = "Cmd"
        else:
            tab_kind_str = tab_kind_map.get(current_tab_info['type'], "Normal")
        return f"{side_name}{tab_suffix}({tab_kind_str})"


    def set_and_get_source_tab_content(self, var, value, source_notebook_ref, source_frame_id_str, current_notebook, current_tab_frame):
        """Helper function to set StringVar and fetch content from another tab."""
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

    def set_and_get_comparison_source_content(self, var, value, source_notebook_ref, source_frame_id_str, current_notebook, current_tab_frame):
        """Fetches content from the comparison target tab and performs comparison."""
        var.set(value)
        
        current_tab_info = self.tab_info_map[current_notebook][str(current_tab_frame)]
        current_tab_info['comparison_source_tab_id'] = (str(source_notebook_ref), source_frame_id_str)

        if source_notebook_ref in self.tab_info_map and source_frame_id_str in self.tab_info_map[source_notebook_ref]:
            source_tab_info = self.tab_info_map[source_notebook_ref][source_frame_id_str]
            current_tab_info['last_comparison_source_content_hash'] = hash(source_tab_info['current_display_content'])
        else:
            current_tab_info['last_comparison_source_content_hash'] = None

        self.apply_comparison(current_notebook, current_tab_frame)


    def get_content_from_other_tab(self, current_notebook, current_tab_frame):
        """Fetches content from another tab and sets it as the current tab's source content."""
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
            self.display_result(current_tab_info['display_widget'], "Could not get source tab content.", state='disabled') 
            current_tab_info['source_content'] = b''
            current_tab_info['last_source_content_hash'] = None 
            self.update_status_label(current_notebook, current_tab_frame)

    def toggle_auto_update(self, notebook_widget, tab_frame):
        """Handles the state change of the auto-update checkbox."""
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
                self.update_status_label(notebook_widget, tab_frame, "Error: Source tab not found.")
        else: 
            self.remove_dependent_tab(notebook_widget, tab_frame)

    def remove_dependent_tab(self, current_notebook, current_tab_frame):
        """Removes a tab from all source dependency lists."""
        dependent_tab_tuple = (str(current_notebook), str(current_tab_frame))
        for source_tab_id, dependents in list(self.dependency_map.items()):
            if dependent_tab_tuple in dependents:
                dependents.remove(dependent_tab_tuple)
            if not dependents: 
                del self.dependency_map[source_tab_id]

    def check_for_auto_updates(self):
        """Periodically checks if source tab content has changed and updates dependent tabs."""
        
        # Check for updates for 'Get from Other Tab' sources
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

        # Check for updates for 'Compare Tab'
        for notebook in [self.left_notebook, self.right_notebook]:
            if notebook in self.tab_info_map:
                for frame_id, tab_info in list(self.tab_info_map[notebook].items()):
                    if tab_info['type'] == 'comparison' and 'comparison_source_tab_id' in tab_info and tab_info['comparison_source_tab_id']:
                        comp_nb_id_str, comp_frame_id_str = tab_info['comparison_source_tab_id']
                        comp_nb = self.get_notebook_from_id_str(comp_nb_id_str)
                        comp_frame = self.get_frame_from_id(comp_nb, comp_frame_id_str)

                        if comp_frame and str(comp_frame) in self.tab_info_map[comp_nb]:
                            comp_source_tab_info = self.tab_info_map[comp_nb][str(comp_frame)]
                            current_comp_content_hash = hash(comp_source_tab_info['current_display_content'])

                            if tab_info['last_comparison_source_content_hash'] != current_comp_content_hash:
                                # Comparison source content changed, re-apply comparison
                                self.apply_comparison(notebook, self.get_frame_from_id(notebook, frame_id))
                                tab_info['last_comparison_source_content_hash'] = current_comp_content_hash
        
        self.root.after(1000, self.check_for_auto_updates) 

    def get_notebook_from_id_str(self, nb_id_str):
        """Helper function to get a notebook widget by its string ID."""
        if str(self.left_notebook) == nb_id_str:
            return self.left_notebook
        elif str(self.right_notebook) == nb_id_str:
            return self.right_notebook
        return None

    def update_tab_display(self, notebook_widget, tab_frame):
        """
        Updates the displayed content based on the current tab type and source content.
        """
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        
        display_state = 'disabled' 
        if current_tab_info['tab_source_var'].get() == "Direct Text Input":
            display_state = 'normal'

        if current_tab_info['tab_source_var'].get() == "Direct Text Input":
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
        elif current_tab_info['type'] == "comparison": # If it's a Compare tab
            self.apply_comparison(notebook_widget, tab_frame)
        else: 
            self.display_result(current_tab_info['display_widget'], current_tab_info['source_content'].decode('utf-8', errors='replace'), state='disabled')
            current_tab_info['current_display_content'] = current_tab_info['source_content']

    def update_source_content_on_key_release(self, notebook_widget, tab_frame):
        """Updates source content when user types in 'Direct Text Input' tab."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        if current_tab_info['tab_source_var'].get() == "Direct Text Input":
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
            elif current_tab_info['type'] == "comparison": # If it's a Compare tab
                self.apply_comparison(notebook_widget, tab_frame)

    def display_result(self, text_widget, content_str, state='normal'):
        """Helper function to update the content of a ScrolledText widget."""
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
            self.update_status_label(notebook_widget, tab_frame, "Filter applied.")
        except re.error as e:
            error_msg_str = f"RegEx error: {e}" 
            error_msg_bytes = error_msg_str.encode('utf-8') 
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled') 
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"Filter apply error: {e}")

    def apply_regex(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        source_content = current_tab_info['source_content'] 
        regex_pattern_bytes = current_tab_info['regex_pattern'].get().encode('utf-8')
        replace_string_bytes = current_tab_info['replace_string'].get().encode('utf-8')

        if not regex_pattern_bytes:
            self.display_result(current_tab_info['display_widget'], "Enter RegEx.", state='disabled') 
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "Replace apply error: No RegEx")
            return

        try:
            replaced_content = re.sub(regex_pattern_bytes, replace_string_bytes, source_content)
            self.display_result(current_tab_info['display_widget'], replaced_content.decode('utf-8', errors='replace'), state='disabled')
            current_tab_info['current_display_content'] = replaced_content
            self.update_status_label(notebook_widget, tab_frame, "Replace applied.")
        except re.error as e:
            error_msg_str = f"RegEx error: {e}" 
            error_msg_bytes = error_msg_str.encode('utf-8') 
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled') 
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"Replace apply error: {e}")

    def apply_line_capture(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        source_content = current_tab_info['source_content'] 
        start_regex_bytes = current_tab_info['start_regex'].get().encode('utf-8')
        end_regex_bytes = current_tab_info['end_regex'].get().encode('utf-8')
        
        lines = source_content.split(b'\n')
        captured_lines = []
        capture_mode = False

        if not start_regex_bytes:
            self.display_result(current_tab_info['display_widget'], "Enter START RegEx.", state='disabled') 
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "Line Capture error: No START RegEx")
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
            self.update_status_label(notebook_widget, tab_frame, "Line Capture applied.")
        except re.error as e:
            error_msg_str = f"RegEx error: {e}" 
            error_msg_bytes = error_msg_str.encode('utf-8') 
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled') 
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"Line Capture error: {e}")
            
    def execute_command(self, notebook_widget, tab_frame):
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        command = current_tab_info['cmd_input_var'].get() 
        file_val = current_tab_info['cmd_f_var'].get() 
        url_val = current_tab_info['cmd_u_var'].get()   
        current_cwd = current_tab_info['current_cwd'] 
        
        if not command.strip():
            self.display_result(current_tab_info['display_widget'], "Enter command to run.", state='disabled') 
            self.update_status_label(notebook_widget, tab_frame, "Cmd exec error: No command")
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
                    output_str = f"Dir changed: {abs_path}\n"
                    output_bytes = output_str.encode('utf-8', errors='replace')
                    current_tab_info['current_display_content'] += output_bytes
                    self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
                    self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']}")
                else:
                    output_str = f"Error: Dir '{new_path}' not found.\n"
                    output_bytes = output_str.encode('utf-8', errors='replace')
                    current_tab_info['current_display_content'] += output_bytes
                    self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
                    self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (CD Error)")
            except Exception as e:
                output_str = f"CD command exec error: {e}\n"
                output_bytes = output_str.encode('utf-8', errors='replace')
                current_tab_info['current_display_content'] += output_bytes
                self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
                self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (CD Error)")
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
                output_bytes += f"Error: ".encode('utf-8') + stderr_bytes
            
            current_tab_info['current_display_content'] += output_bytes
            self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
            self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (Cmd Exec Complete)")

        except Exception as e:
            error_output_str = f"$ {processed_command}\nError: {e}\n"
            error_output_bytes = error_output_str.encode('utf-8', errors='replace')
            current_tab_info['current_display_content'] += error_output_bytes
            self.display_result(current_tab_info['display_widget'], current_tab_info['current_display_content'].decode('utf-8', errors='replace'), state='disabled')
            self.update_status_label(notebook_widget, tab_frame, f"CWD: {current_tab_info['current_cwd']} (Cmd Exec Error)")

    def _get_number_value(self, word_bytes, number_type):
        """Converts a number represented as bytes string (decimal or hex) to an int/float,
        cleaning non-relevant characters based on type."""
        word_str = word_bytes.decode('utf-8', errors='ignore') # Use ignore for decoding errors

        if number_type == 'decimal':
            # Keep only digits and periods for decimal conversion
            cleaned_str = re.sub(r'[^0-9.]', '', word_str)
            if not cleaned_str: return None
            try:
                if '.' in cleaned_str:
                    return float(cleaned_str)
                else:
                    return int(cleaned_str)
            except ValueError:
                return None
        elif number_type == 'hex':
            # Keep only hex digits and '0x' prefix
            lower_word_str = word_str.lower()
            if lower_word_str.startswith('0x'):
                # Extract hex part after '0x' and clean it
                hex_part = lower_word_str[2:]
                cleaned_hex_part = re.sub(r'[^0-9a-f]', '', hex_part)
                if not cleaned_hex_part: return None # No hex chars left after 0x
                cleaned_str = '0x' + cleaned_hex_part
            else:
                # This case should ideally not be hit if regex is strict with '0x' prefix
                # But if it is, just clean all non-hex chars and prepend '0x'
                cleaned_str_no_prefix = re.sub(r'[^0-9a-f]', '', lower_word_str)
                if not cleaned_str_no_prefix: return None
                cleaned_str = '0x' + cleaned_str_no_prefix

            try:
                return int(cleaned_str, 16)
            except ValueError:
                return None
        return None

    def apply_comparison(self, notebook_widget, tab_frame):
        """Core logic for Compare tab: Compares numbers between two sources and displays change percentage."""
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        current_source_content = current_tab_info['source_content'] # Current tab's source content (bytes)

        # Get content of the comparison target tab.
        comparison_tab_id = current_tab_info.get('comparison_source_tab_id')
        if not comparison_tab_id:
            self.display_result(current_tab_info['display_widget'], "Select comparison target tab.", state='disabled')
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "Compare error: No target tab")
            return

        comp_nb = self.get_notebook_from_id_str(comparison_tab_id[0])
        comp_frame = self.get_frame_from_id(comp_nb, comparison_tab_id[1])

        if not comp_frame or str(comp_frame) not in self.tab_info_map[comp_nb]:
            self.display_result(current_tab_info['display_widget'], "Selected comparison target tab not found.", state='disabled')
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "Compare error: Target tab not found")
            return
        
        comparison_content = self.tab_info_map[comp_nb][str(comp_frame)]['current_display_content'] # Current display content of comparison target tab (bytes)

        # Get number RegExes.
        decimal_regex_bytes = current_tab_info['decimal_regex_var'].get().encode('utf-8')
        hex_regex_bytes = current_tab_info['hex_regex_var'].get().encode('utf-8')
        
        enable_decimal = current_tab_info['enable_decimal_var'].get()
        enable_hex = current_tab_info['enable_hex_var'].get()

        if not (enable_decimal or enable_hex):
            self.display_result(current_tab_info['display_widget'], "Enable at least one of Decimal or Hex RegEx.", state='disabled')
            current_tab_info['current_display_content'] = b''
            self.update_status_label(notebook_widget, tab_frame, "Compare error: RegEx disabled")
            return

        try:
            decimal_pattern = re.compile(decimal_regex_bytes) if enable_decimal else None
            hex_pattern = re.compile(hex_regex_bytes) if enable_hex else None
        except re.error as e:
            error_msg_str = f"RegEx error: {e}"
            error_msg_bytes = error_msg_str.encode('utf-8')
            self.display_result(current_tab_info['display_widget'], error_msg_str, state='disabled')
            current_tab_info['current_display_content'] = error_msg_bytes
            self.update_status_label(notebook_widget, tab_frame, f"Compare apply error: {e}")
            return

        processed_lines = []
        current_lines = current_source_content.split(b'\n')
        comparison_lines = comparison_content.split(b'\n')

        for i, current_line in enumerate(current_lines):
            annotated_words = []
            current_words = current_line.split(b' ')

            if i < len(comparison_lines):
                comparison_line = comparison_lines[i]
                comparison_words = comparison_line.split(b' ')
            else:
                comparison_words = [] # No line to compare, so empty list

            for j, current_word in enumerate(current_words):
                comparison_word = comparison_words[j] if j < len(comparison_words) else b''
                
                current_val = None
                comparison_val = None
                
                # Apply Hex RegEx first (priority)
                if enable_hex and hex_pattern and hex_pattern.fullmatch(current_word):
                    current_val = self._get_number_value(current_word, 'hex') # Pass 'hex' type
                elif enable_decimal and decimal_pattern and decimal_pattern.fullmatch(current_word):
                    current_val = self._get_number_value(current_word, 'decimal') # Pass 'decimal' type
                
                if enable_hex and hex_pattern and hex_pattern.fullmatch(comparison_word):
                    comparison_val = self._get_number_value(comparison_word, 'hex') # Pass 'hex' type
                elif enable_decimal and decimal_pattern and decimal_pattern.fullmatch(comparison_word):
                    comparison_val = self._get_number_value(comparison_word, 'decimal') # Pass 'decimal' type

                if current_val is not None and comparison_val is not None:
                    try:
                        if comparison_val == 0:
                            if current_val > 0:
                                annotated_words.append(current_word + b'(+Inf%)')
                            elif current_val < 0:
                                annotated_words.append(current_word + b'(-Inf%)')
                            else: # current_val is also 0
                                annotated_words.append(current_word + b'(0%)')
                        else:
                            percentage_change = ((current_val - comparison_val) / comparison_val) * 100
                            annotated_words.append(current_word + f'({percentage_change:.1f}%)'.encode('utf-8'))
                    except Exception as e:
                        # If number conversion or calculation error, keep original word
                        annotated_words.append(current_word)
                        print(f"Error during comparison for word '{current_word.decode()}' vs '{comparison_word.decode()}': {e}")
                else:
                    annotated_words.append(current_word)
            processed_lines.append(b' '.join(annotated_words))
        
        processed_content = b"\n".join(processed_lines)
        self.display_result(current_tab_info['display_widget'], processed_content.decode('utf-8', errors='replace'), state='disabled')
        current_tab_info['current_display_content'] = processed_content
        self.update_status_label(notebook_widget, tab_frame, "Compare applied.")


    def update_status_label(self, notebook_widget, tab_frame, custom_message=None):
        """
        Updates the status label of the given tab with relevant information.
        If custom_message is provided, it takes precedence.
        """
        current_tab_info = self.tab_info_map[notebook_widget][str(tab_frame)]
        status_label = current_tab_info['status_label']
        
        status_text = ""
        if custom_message:
            status_text = custom_message
        else:
            tab_source_type = current_tab_info['tab_source_var'].get()
            tab_logic_type = current_tab_info['type']
            
            if tab_source_type == "Load from File":
                status_text = "Loaded from file"
            elif tab_source_type == "Direct Text Input":
                status_text = "Direct text input"
            elif tab_source_type == "Get from Other Tab":
                status_text = f"Got from '{current_tab_info['selected_source_tab'].get()}' tab"
            elif tab_source_type == "Cmdline":
                status_text = f"CWD: {current_tab_info['current_cwd']}" 
            
            if tab_logic_type == "comparison": # For Compare tab
                comp_tab_name = current_tab_info['comparison_source_tab_var'].get()
                if comp_tab_name and comp_tab_name != "No Tabs Available":
                    status_text = f"Comparing with '{comp_tab_name}' tab"
                else:
                    status_text = "Select comparison target tab"
                
                if not current_tab_info['current_display_content'].strip():
                    status_text += " (No content)"
                else:
                    status_text += " (Compare applied)"

            elif tab_source_type != "Cmdline": 
                if tab_logic_type == "filter":
                    status_text += " (Filter pending)" if not current_tab_info['current_display_content'].strip() else " (Filter applied)"
                elif tab_logic_type == "replace":
                    status_text += " (Replace pending)" if not current_tab_info['current_display_content'].strip() else " (Replace applied)"
                elif tab_logic_type == "line_capture":
                    status_text += " (Line Capture pending)" if not current_tab_info['current_display_content'].strip() else " (Line Capture applied)"
                else: 
                    if not current_tab_info['source_content'].strip() and tab_source_type != "Direct Text Input":
                         status_text += " (No content)"

        status_label.config(text=status_text)

    def close_tab_from_button(self, notebook_widget, tab_frame):
        """Removes a tab when 'Close Tab' button is clicked."""
        tab_id = tab_frame.winfo_id()
        for i, frame_id in enumerate(notebook_widget.tabs()):
            if notebook_widget.nametowidget(frame_id) == tab_frame:
                self.remove_dependent_tab(notebook_widget, tab_frame)
                del self.tab_info_map[notebook_widget][str(tab_frame)]
                notebook_widget.forget(i)
                break
        
        if not notebook_widget.tabs():
            side_name = "L" if notebook_widget == self.left_notebook else "R"
            self.add_new_tab(notebook_widget, side_name)


if __name__ == "__main__":
    root = tk.Tk()
    app = FileViewerApp(root)
    root.mainloop()
