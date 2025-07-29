import sys
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, font, ttk
import difflib
import traceback
from io import BytesIO
import os
import subprocess # For objdump and readelf

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.dwarf.die import DIE
from elftools.dwarf.enums import ENUM_DW_AT, ENUM_DW_TAG
from capstone import (
    Cs,
    CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB,
    CS_ARCH_ARM64,
    CS_ARCH_X86, CS_MODE_32, CS_MODE_64,
    CS_MODE_LITTLE_ENDIAN, CS_MODE_BIG_ENDIAN
)

class ELFComparerApp:
    """
    A GUI application to compare two ELF files, with support for multiple architectures.
    Includes symbol filtering, absolute path handling, and compilation options comparison.
    Allows selection between Capstone and objdump for disassembly.
    Now allows setting custom paths for external tools like objdump and readelf.
    """
    def __init__(self, master, file1=None, file2=None):
        self.master = master
        self.master.title("ELF Comparison Tool (Multi-Architecture Support)")
        self.master.geometry("1600x1000")

        self.file1_path = tk.StringVar(value=os.path.abspath(file1) if file1 else "")
        self.file2_path = tk.StringVar(value=os.path.abspath(file2) if file2 else "")

        self.elf1 = None # Will still load elftools ELFFile for internal Capstone/DWARF
        self.elf2 = None # Will still load elftools ELFFile for internal Capstone/DWARF
        
        # Initial Capstone disassemblers, used for architectures without specific mode switching (e.g., x86-64, AArch64)
        # For ARM, new Cs instances are created per function to handle ARM/Thumb modes.
        self.md1_base = None
        self.md2_base = None
        self.arch_name1 = "Unknown"
        self.arch_name2 = "Unknown"

        self.functions1 = {} # Populated from all_symbols1, filtered for STT_FUNC
        self.functions2 = {} # Populated from all_symbols2, filtered for STT_FUNC
        self.all_symbols1 = {} # Now populated by _get_all_symbols_from_readelf
        self.all_symbols2 = {} # Now populated by _get_all_symbols_from_readelf

        # Symbol Type Filter
        self.filter_type = tk.StringVar(value="All Symbols")
        self.filter_options = ["All Symbols", "Functions", "Objects", "Notype", "Other Types"]
        
        # Symbol Status Filter (Modified, Unchanged, etc.)
        self.filter_status = tk.StringVar(value="All Status")
        self.filter_status_options = ["All Status", "Added", "Deleted", "Modified", "Unchanged"]

        # Disassembly Method Selection
        self.disassembly_method = tk.StringVar(value="Capstone (Internal)")
        self.disassembly_method_options = ["Capstone (Internal)", "objdump (External)"]

        # External Tool Paths
        self.objdump_path = tk.StringVar(value=self._get_default_tool_path("objdump"))
        self.readelf_path = tk.StringVar(value=self._get_default_tool_path("readelf"))

        self.mono_font = font.Font(family="Courier New", size=10)

        self._create_widgets()

        if self.file1_path.get() and self.file2_path.get():
            print(f"[DEBUG] Initializing with files: {self.file1_path.get()}, {self.file2_path.get()}")
            self.master.after(100, self._load_and_parse_files)
        else:
            print("[DEBUG] No initial files provided. Please select files using GUI.")

    def _get_default_tool_path(self, tool_name):
        """Attempts to find a default path for common tools."""
        if sys.platform == "win32":
            return tool_name + ".exe"
        else:
            return tool_name

    def _create_widgets(self):
        # --- Top Frame for file selection ---
        top_frame = tk.Frame(self.master, padx=10, pady=10, bd=2, relief=tk.GROOVE)
        top_frame.pack(fill=tk.X)

        tk.Button(top_frame, text="Open ELF File 1", command=self._open_file1).pack(side=tk.LEFT, padx=5)
        tk.Entry(top_frame, textvariable=self.file1_path, width=40, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(top_frame, text="Open ELF File 2", command=self._open_file2).pack(side=tk.LEFT, padx=(20, 5))
        tk.Entry(top_frame, textvariable=self.file2_path, width=40, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(top_frame, text="Load & Parse Files", command=self._load_and_parse_files, font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=15)

        # --- External Tools Path Configuration Frame ---
        tool_path_frame = tk.LabelFrame(self.master, text="External Tool Paths", padx=10, pady=5, bd=2, relief=tk.GROOVE)
        tool_path_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # objdump path
        tk.Label(tool_path_frame, text="objdump Path:").pack(side=tk.LEFT, padx=(0, 5))
        tk.Entry(tool_path_frame, textvariable=self.objdump_path, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(tool_path_frame, text="Browse", command=lambda: self._browse_tool_path(self.objdump_path)).pack(side=tk.LEFT, padx=5)

        # readelf path
        tk.Label(tool_path_frame, text="readelf Path:").pack(side=tk.LEFT, padx=(15, 5))
        tk.Entry(tool_path_frame, textvariable=self.readelf_path, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(tool_path_frame, text="Browse", command=lambda: self._browse_tool_path(self.readelf_path)).pack(side=tk.LEFT, padx=5)


        # --- Main Content Frame ---
        main_content_frame = tk.Frame(self.master, padx=10, pady=5)
        main_content_frame.pack(fill=tk.BOTH, expand=True)

        # --- Left Panel for Symbol List and Overview ---
        left_panel = tk.Frame(main_content_frame, width=300, bd=2, relief=tk.SUNKEN)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        tk.Label(left_panel, text="Select Comparison Item:", font=("Helvetica", 10, "bold")).pack(pady=(5, 2))

        # Overview buttons
        overview_frame = tk.Frame(left_panel)
        overview_frame.pack(fill=tk.X, pady=5)
        tk.Button(overview_frame, text="Compare ELF Headers", command=self._display_header_comparison).pack(fill=tk.X, pady=2, padx=5)
        tk.Button(overview_frame, text="Compare Section Headers", command=self._display_section_comparison).pack(fill=tk.X, pady=2, padx=5)
        tk.Button(overview_frame, text="Compare Symbol Tables", command=self._display_symbol_comparison).pack(fill=tk.X, pady=2, padx=5)
        
        # Compare Compilation Options Button (above symbol list filters)
        tk.Button(overview_frame, text="Compare Compilation Options", command=self._display_compilation_options_comparison).pack(fill=tk.X, pady=(10, 2), padx=5)


        tk.Label(left_panel, text="Symbol List:", font=("Helvetica", 10, "bold")).pack(pady=(10, 2))

        # Disassembly Method Combobox
        disasm_method_frame = tk.Frame(left_panel)
        disasm_method_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(disasm_method_frame, text="Disassembly Method:").pack(side=tk.LEFT)
        self.disassembly_method_combobox = ttk.Combobox(disasm_method_frame, textvariable=self.disassembly_method,
                                                        values=self.disassembly_method_options, state="readonly", width=15)
        self.disassembly_method_combobox.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        # No bind to this combobox, the selection will be read directly when disassembly is requested.

        # Symbol Type Filter Combobox
        filter_type_frame = tk.Frame(left_panel)
        filter_type_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(filter_type_frame, text="Filter by Type:").pack(side=tk.LEFT)
        self.filter_combobox_type = ttk.Combobox(filter_type_frame, textvariable=self.filter_type, 
                                            values=self.filter_options, state="readonly", width=15)
        self.filter_combobox_type.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        self.filter_combobox_type.bind("<<ComboboxSelected>>", self._on_type_filter_select)

        # Symbol Status Filter (Modified, Unchanged, etc.) Combobox
        filter_status_frame = tk.Frame(left_panel)
        filter_status_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(filter_status_frame, text="Filter by Symbol Status:").pack(side=tk.LEFT)
        self.filter_combobox_status = ttk.Combobox(filter_status_frame, textvariable=self.filter_status,
                                                  values=self.filter_status_options, state="readonly", width=15)
        self.filter_combobox_status.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        self.filter_combobox_status.bind("<<ComboboxSelected>>", self._on_status_filter_select)


        self.function_list_frame = tk.Frame(left_panel)
        self.function_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        self.function_list = tk.Listbox(self.function_list_frame, font=self.mono_font, width=40, height=20, exportselection=False)
        self.function_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.function_list_scrollbar = tk.Scrollbar(self.function_list_frame, orient=tk.VERTICAL, command=self.function_list.yview)
        self.function_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.function_list.config(yscrollcommand=self.function_list_scrollbar.set)
        self.function_list.bind('<<ListboxSelect>>', self._on_symbol_select)


        # --- Right Panel for Comparison Results ---
        right_panel = tk.Frame(main_content_frame, bd=2, relief=tk.SUNKEN)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Labels for file paths above text widgets
        label_frame = tk.Frame(right_panel)
        label_frame.pack(fill=tk.X)
        tk.Label(label_frame, textvariable=self.file1_path, font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        tk.Label(label_frame, textvariable=self.file2_path, font=("Helvetica", 9, "bold")).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 10))


        # --- Text widgets for side-by-side view ---
        self.text1 = scrolledtext.ScrolledText(right_panel, wrap=tk.NONE, font=self.mono_font, width=70)
        self.text1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 2))

        self.text2 = scrolledtext.ScrolledText(right_panel, wrap=tk.NONE, font=self.mono_font, width=70)
        self.text2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 5))

        # --- Configure tags for highlighting differences ---
        self.text1.tag_config('diff', background='#FFDDDD')
        self.text2.tag_config('diff', background='#DDFFDD')
        self.text1.tag_config('added', background='#CCFFCC')
        self.text2.tag_config('deleted', background='#FFCCCC')
        self.text1.tag_config('header', foreground='blue', font=(self.mono_font.cget('family'), self.mono_font.cget('size'), 'bold'))
        self.text2.tag_config('header', foreground='blue', font=(self.mono_font.cget('family'), self.mono_font.cget('size'), 'bold'))


        # --- Synchronize scrolling ---
        self.text1.vbar.config(command=self._scroll_both)
        self.text2.vbar.config(command=self._scroll_both)
        self.text1.config(yscrollcommand=self._update_scroll_from_text1)
        self.text2.config(yscrollcommand=self._update_scroll_from_text2)

    def _scroll_both(self, *args):
        self.text1.yview_moveto(args[0])
        self.text2.yview_moveto(args[0])

    def _update_scroll_from_text1(self, first, last):
        self.text2.yview_moveto(first)
        self.text1.vbar.set(first, last)
        self.text2.vbar.set(first, last)

    def _update_scroll_from_text2(self, first, last):
        self.text1.yview_moveto(first)
        self.text2.vbar.set(first, last)
        self.text1.vbar.set(first, last)

    def _open_file1(self):
        path = filedialog.askopenfilename(title="Select First ELF File")
        if path:
            self.file1_path.set(os.path.abspath(path))
            print(f"[DEBUG] File 1 selected: {self.file1_path.get()}")
            self._clear_data()

    def _open_file2(self):
        path = filedialog.askopenfilename(title="Select Second ELF File")
        if path:
            self.file2_path.set(os.path.abspath(path))
            print(f"[DEBUG] File 2 selected: {self.file2_path.get()}")
            self._clear_data()

    def _browse_tool_path(self, path_var):
        """Opens a file dialog to select an executable tool path."""
        initial_dir = os.path.dirname(path_var.get()) if path_var.get() and os.path.exists(os.path.dirname(path_var.get())) else os.getcwd()

        path = filedialog.askopenfilename(
            title="Select Tool Executable",
            initialdir=initial_dir,
            filetypes=[("Executables", "*"), ("All Files", "*.*")]
        )
        if path:
            path_var.set(os.path.abspath(path))
            print(f"[DEBUG] Tool path updated: {path_var.get()}")


    def _clear_data(self):
        print("[DEBUG] Clearing previous data.")
        # self.elf1 and self.elf2 will still be used by Capstone and DWARF extraction
        # but their contents are reset when new files are loaded.
        self.elf1 = None
        self.elf2 = None
        self.md1_base = None
        self.md2_base = None
        self.arch_name1 = "Unknown"
        self.arch_name2 = "Unknown"
        self.functions1 = {}
        self.functions2 = {}
        self.all_symbols1 = {} # This will now be populated by readelf
        self.all_symbols2 = {} # This will now be populated by readelf
        self.function_list.delete(0, tk.END)
        self._clear_texts()

    def _get_disassembler(self, elf):
        """
        Returns a Capstone instance and architecture name for the given ELF file.
        Includes endianness setting.
        This still relies on elftools for ELF header parsing.
        """
        endian_mode = CS_MODE_LITTLE_ENDIAN
        if elf.header['e_ident']['EI_DATA'] == 'ELFDATA2MSB':
            endian_mode = CS_MODE_BIG_ENDIAN
            print(f"[DEBUG] Detected Big-Endian for ELF file.")
        else:
            print(f"[DEBUG] Detected Little-Endian (default) for ELF file.")


        arch_map = {
            'EM_ARM': (CS_ARCH_ARM, CS_MODE_ARM, "ARM"),
            'EM_AARCH64': (CS_ARCH_ARM64, CS_MODE_ARM, "AArch64"),
            'EM_X86_64': (CS_ARCH_X86, CS_MODE_64, "x86-64"),
            'EM_386': (CS_ARCH_X86, CS_MODE_32, "x86 (32-bit)"),
        }
        machine = elf['e_machine']
        for key, (arch, mode, name) in arch_map.items():
            if elf.header.e_machine == key:
                print(f"[DEBUG] Detected architecture: {name} (Machine: {key})")
                return Cs(arch, mode | endian_mode), name
        print(f"[DEBUG] Unknown architecture detected: {machine}")
        return None, "Unknown"

    def _load_and_parse_files(self):
        path1 = self.file1_path.get()
        path2 = self.file2_path.get()

        if not path1 or not path2:
            messagebox.showerror("Error", "Please select both ELF files.")
            print("[DEBUG] Error: Both file paths not selected.")
            return

        self._clear_data()
        print(f"[DEBUG] Attempting to load and parse files:\n   File 1: {path1}\n   File 2: {path2}")

        try:
            # Load ELF files with elftools for header/section/DWARF info
            # This is still needed for Capstone and DWARF compilation options comparison
            with open(path1, 'rb') as f1_stream:
                f1_data = BytesIO(f1_stream.read())
            self.elf1 = ELFFile(f1_data)
            self.md1_base, self.arch_name1 = self._get_disassembler(self.elf1)
            if self.md1_base is None:
                messagebox.showerror("Error", f"Unsupported architecture for File 1: {self.arch_name1}")
                self._clear_data()
                print(f"[DEBUG] Error: File 1 unsupported architecture: {self.arch_name1}")
                return

            with open(path2, 'rb') as f2_stream:
                f2_data = BytesIO(f2_stream.read())
            self.elf2 = ELFFile(f2_data)
            self.md2_base, self.arch_name2 = self._get_disassembler(self.elf2)
            if self.md2_base is None:
                messagebox.showerror("Error", f"Unsupported architecture for File 2: {self.arch_name2}")
                self._clear_data()
                print(f"[DEBUG] Error: File 2 unsupported architecture: {self.arch_name2}")
                return

            if self.arch_name1 != self.arch_name2:
                messagebox.showwarning("Warning", f"Architectures of the two files differ: ({self.arch_name1} vs {self.arch_name2}).\nComparison results might not be meaningful.")

            print("[DEBUG] Extracting functions/symbols from files using readelf...")
            # Use external readelf to get symbol info
            self.all_symbols1 = self._get_all_symbols_from_readelf(self.file1_path.get())
            self.all_symbols2 = self._get_all_symbols_from_readelf(self.file2_path.get())
            
            # Filter functions from the readelf-derived symbols
            self.functions1 = {name: info for name, info in self.all_symbols1.items() if info['type'] == 'STT_FUNC'}
            self.functions2 = {name: info for name, info in self.all_symbols2.items() if info['type'] == 'STT_FUNC'}

            print(f"[DEBUG] Found {len(self.all_symbols1)} symbols ({len(self.functions1)} functions) in File 1 (via readelf).")
            print(f"[DEBUG] Found {len(self.all_symbols2)} symbols ({len(self.functions2)} functions) in File 2 (via readelf).")

            self._populate_symbol_list()
            self._display_header_comparison()
            print("[DEBUG] Files loaded and parsed successfully. Displaying header comparison.")

        except FileNotFoundError as e:
            messagebox.showerror("File Not Found Error", f"File not found: {e.filename}\nPlease check the path.")
            print(f"[DEBUG] FileNotFoundError: {e.filename}. Traceback:\n{traceback.format_exc()}")
            self._clear_data()
        except Exception as e:
            messagebox.showerror("General Error", f"An error occurred during file loading and parsing: {e}\nCheck console for details.")
            print(f"[DEBUG] An unexpected error occurred during file loading/parsing: {e}. Traceback:\n{traceback.format_exc()}")
            self._clear_data()
        finally:
            self.master.update_idletasks()

    def _get_all_symbols_from_readelf(self, file_path):
        """
        Extracts all symbols from the symbol table of an ELF file using the external readelf tool.
        Returns a dictionary of symbol_name -> {addr, size, type, bind, section_index}.
        """
        symbols = {}
        readelf_cmd = self.readelf_path.get()
        if not readelf_cmd:
            messagebox.showerror("Error", "readelf path is not set. Please configure it in 'External Tool Paths'.")
            return {}
        
        # Check if readelf exists and is executable
        if not os.path.exists(readelf_cmd) or not os.access(readelf_cmd, os.X_OK):
            if os.path.basename(readelf_cmd).lower() in ["readelf", "readelf.exe"]:
                pass # Assume it's in PATH if just the name is given
            else:
                messagebox.showerror("Error", f"The configured readelf path '{readelf_cmd}' is not a valid executable.")
                return {}

        try:
            # Use 'readelf -Ws' for comprehensive symbol table output
            command = [readelf_cmd, "-Ws", file_path]
            print(f"[DEBUG] Running readelf command for symbols: {' '.join(command)}")
            
            process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
            output_lines = process.stdout.splitlines()

            # Parse readelf -Ws output
            # Example line:
            # Num:    Value          Size Type    Bind   Vis      Ndx Name
            #   0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND 
            #   1: 0000000000012345    60 FUNC    GLOBAL DEFAULT   12 my_function
            
            for line in output_lines:
                # Skip header lines and empty lines
                if not line.strip() or "Num:" in line or "Value" in line:
                    continue
                
                parts = line.split()
                try:
                    # Adjust parsing based on typical readelf -Ws output format
                    # Num: Value Size Type Bind Vis Ndx Name
                    # For a global function: ['1:', '0000000000012345', '60', 'FUNC', 'GLOBAL', 'DEFAULT', '12', 'my_function']
                    # Some versions might have different spacing or extra columns
                    
                    # Try to find the 'Name' part more robustly, typically it's the last one
                    if len(parts) < 8: # Minimum expected parts for a symbol line
                        continue
                    
                    # Assuming Ndx is usually before Name, and Name is last
                    name = parts[-1]
                    ndx_str = parts[-2]
                    vis = parts[-3] # Vis can be DEFAULT, HIDDEN, PROTECTED, INTERNAL
                    bind_str = parts[-4] # GLOBAL, LOCAL, WEAK
                    type_str = parts[-5] # FUNC, OBJECT, NOTYPE, FILE, SECTION, etc.
                    size_str = parts[-6]
                    value_str = parts[-7] # Hex address

                    # Convert to appropriate types
                    addr = int(value_str, 16)
                    size = int(size_str)
                    
                    # Map readelf types to elftools STT_ constants if needed, or use directly
                    # For now, we'll use readelf's type string (e.g., 'FUNC', 'OBJECT') and add STT_ prefix
                    sym_type = f"STT_{type_str.upper()}" if type_str else "STT_NOTYPE"
                    sym_bind = f"STB_{bind_str.upper()}" if bind_str else "STB_LOCAL"

                    # Ndx can be section number or special values (UND, ABS, COMMON)
                    section_index = None
                    if ndx_str.isdigit():
                        section_index = int(ndx_str)
                    elif ndx_str == 'UND':
                        section_index = 'SHN_UNDEF'
                    elif ndx_str == 'ABS':
                        section_index = 'SHN_ABS'
                    elif ndx_str == 'COM': # Common block
                        section_index = 'SHN_COMMON'
                    else:
                        section_index = ndx_str # Keep as string if unknown special value
                        
                    # Filter out undefined symbols unless specifically needed for other purposes
                    if section_index == 'SHN_UNDEF':
                        continue

                    if name: # Ensure name is not empty
                        symbols[name] = {
                            'addr': addr,
                            'size': size,
                            'section_index': section_index, # Store as int or special string
                            'type': sym_type,
                            'bind': sym_bind
                        }
                except (ValueError, IndexError) as parse_e:
                    print(f"[DEBUG] Failed to parse readelf line: '{line.strip()}' - Error: {parse_e}")
                    continue # Skip malformed lines

        except FileNotFoundError:
            messagebox.showerror("Error", f"readelf command '{readelf_cmd}' not found.\nPlease ensure Binutils is installed and readelf is in your system PATH, or set the correct path in 'External Tool Paths'.")
            print(f"[DEBUG] readelf command '{readelf_cmd}' not found. Traceback:\n{traceback.format_exc()}")
            return {}
        except subprocess.CalledProcessError as e:
            messagebox.showerror("readelf Error", f"readelf execution failed: {e.stderr}")
            print(f"[DEBUG] readelf execution failed. Error: {e.stderr}. Traceback:\n{traceback.format_exc()}")
            return {}
        except Exception as e:
            print(f"[DEBUG] Unexpected error during readelf symbol extraction: {e}. Traceback:\n{traceback.format_exc()}")
            return {}
        return symbols


    def _populate_symbol_list(self):
        """Populates the symbol listbox based on the currently selected type and symbol status filters."""
        print("[DEBUG] Populating symbol list based on filter...")
        self.function_list.delete(0, tk.END)

        current_type_filter = self.filter_type.get()
        current_status_filter = self.filter_status.get()

        all_symbol_names = sorted(list(set(self.all_symbols1.keys()) | set(self.all_symbols2.keys())))
        
        if not all_symbol_names:
            self.function_list.insert(tk.END, "No symbols found.")
            print("[DEBUG] No symbols found in either ELF file.")
            return

        displayed_count = 0
        for name in all_symbol_names:
            if not name: continue
            
            sym1 = self.all_symbols1.get(name)
            sym2 = self.all_symbols2.get(name)

            # --- Determine Symbol Status (Added, Deleted, Modified, Unchanged etc.) ---
            symbol_status_text = ""
            if name in self.all_symbols1 and name not in self.all_symbols2:
                symbol_status_text = "Deleted"
            elif name not in self.all_symbols1 and name in self.all_symbols2:
                symbol_status_text = "Added"
            elif name in self.all_symbols1 and name in self.all_symbols2:
                is_modified = False
                # Compare relevant symbol properties
                if (sym1['addr'] != sym2['addr'] or 
                    sym1['size'] != sym2['size'] or
                    sym1['type'] != sym2['type'] or
                    sym1['bind'] != sym2['bind']):
                    is_modified = True
                if is_modified:
                    symbol_status_text = "Modified"
                else:
                    symbol_status_text = "Unchanged"
            
            # --- Apply Type Filter ---
            display_by_type = False
            sym_type1 = sym1['type'] if sym1 else None
            sym_type2 = sym2['type'] if sym2 else None

            if current_type_filter == "All Symbols":
                display_by_type = True
            elif current_type_filter == "Functions":
                if (sym1 and sym_type1 == 'STT_FUNC') or \
                   (sym2 and sym_type2 == 'STT_FUNC'):
                    display_by_type = True
            elif current_type_filter == "Objects":
                if (sym1 and sym_type1 == 'STT_OBJECT') or \
                   (sym2 and sym_type2 == 'STT_OBJECT'):
                    display_by_type = True
            elif current_type_filter == "Notype":
                if (sym1 and sym_type1 == 'STT_NOTYPE') or \
                   (sym2 and sym_type2 == 'STT_NOTYPE'):
                    display_by_type = True
            elif current_type_filter == "Other Types":
                # Check for other STT_ values not explicitly listed
                if (sym1 and sym_type1 not in ['STT_FUNC', 'STT_OBJECT', 'STT_NOTYPE']) or \
                   (sym2 and sym_type2 not in ['STT_FUNC', 'STT_OBJECT', 'STT_NOTYPE']):
                    display_by_type = True

            # --- Apply Symbol Status Filter (Modified, Unchanged, etc.) ---
            display_by_symbol_status = False
            if current_status_filter == "All Status" or current_status_filter == symbol_status_text:
                display_by_symbol_status = True

            # Display if all filters pass
            if display_by_type and display_by_symbol_status:
                type_suffix = ""
                # Attempt to show type from common symbol if both exist and are same type
                if sym1 and sym2 and sym1['type'] == sym2['type']:
                    type_suffix = f" ({sym1['type'].replace('STT_', '')})"
                elif sym1:
                    type_suffix = f" (F1: {sym1['type'].replace('STT_', '')})"
                elif sym2:
                    type_suffix = f" (F2: {sym2['type'].replace('STT_', '')})"

                self.function_list.insert(tk.END, f"{name} ({symbol_status_text}){type_suffix}")
                displayed_count += 1
        print(f"[DEBUG] Symbol list populated with {displayed_count} entries (Type: {current_type_filter}, Symbol Status: {current_status_filter}).")


    def _on_type_filter_select(self, event):
        """Callback for when a symbol type filter is selected."""
        print(f"[DEBUG] Symbol type filter changed to: {self.filter_type.get()}")
        self._populate_symbol_list()

    def _on_status_filter_select(self, event):
        """Callback for when a symbol status filter is selected."""
        print(f"[DEBUG] Symbol status filter changed to: {self.filter_status.get()}")
        self._populate_symbol_list()


    def _add_content(self, content1_lines, content2_lines, tag1=None, tag2=None):
        """Helper to add content to text widgets with optional highlighting.
        content1_lines and content2_lines are lists of strings."""
        self.text1.config(state=tk.NORMAL)
        self.text2.config(state=tk.NORMAL)

        max_lines = max(len(content1_lines), len(content2_lines))

        for i in range(max_lines):
            line1 = content1_lines[i] if i < len(content1_lines) else ""
            line2 = content2_lines[i] if i < len(content2_lines) else ""

            start_index1 = self.text1.index(tk.END)
            start_index2 = self.text2.index(tk.END)

            self.text1.insert(tk.END, line1 + "\n")
            self.text2.insert(tk.END, line2 + "\n")

            end_index1 = self.text1.index(f"{start_index1} + {len(line1)}c")
            end_index2 = self.text2.index(f"{start_index2} + {len(line2)}c")

            if line1 and tag1:
                self.text1.tag_add(tag1, start_index1, end_index1)
            if line2 and tag2:
                self.text2.tag_add(tag2, start_index2, end_index2)
            
        self.text1.config(state=tk.DISABLED)
        self.text2.config(state=tk.DISABLED)
        self.master.update_idletasks()

    def _add_title(self, title):
        separator = "=" * 30
        self.text1.config(state=tk.NORMAL)
        self.text2.config(state=tk.NORMAL)
        
        self.text1.insert(tk.END, f"\n{separator}\n{title}\n{separator}\n", 'header')
        self.text2.insert(tk.END, f"\n{separator}\n{title}\n{separator}\n", 'header')
        
        self.text1.config(state=tk.DISABLED)
        self.text2.config(state=tk.DISABLED)

    def _clear_texts(self):
        self.text1.config(state=tk.NORMAL)
        self.text2.config(state=tk.NORMAL)
        self.text1.delete('1.0', tk.END)
        self.text2.delete('1.0', tk.END)
        self.text1.config(state=tk.DISABLED)
        self.text2.config(state=tk.DISABLED)

    def _display_header_comparison(self):
        print("[DEBUG] Displaying ELF Header Comparison.")
        if not self.elf1 or not self.elf2:
            messagebox.showinfo("Info", "Please load both ELF files first.")
            return

        self._clear_texts()
        self._add_title("ELF Header Comparison")
        header1 = self.elf1.header
        header2 = self.elf2.header
        
        lines1 = []
        lines2 = []
        tags1 = []
        tags2 = []

        for key in header1.keys():
            val1 = str(header1[key])
            val2 = str(header2[key])
            line1 = f"{key:<20}: {val1}"
            line2 = f"{key:<20}: {val2}"
            lines1.append(line1)
            lines2.append(line2)

            if val1 != val2:
                tags1.append('diff')
                tags2.append('diff')
            else:
                tags1.append(None)
                tags2.append(None)
        
        for i in range(len(lines1)):
            self._add_content([lines1[i]], [lines2[i]], tags1[i], tags2[i])
        print("[DEBUG] ELF Header Comparison displayed.")

    def _display_section_comparison(self):
        print("[DEBUG] Displaying Section Header Comparison.")
        if not self.elf1 or not self.elf2:
            messagebox.showinfo("Info", "Please load both ELF files first.")
            return

        self._clear_texts()
        self._add_title("Section Header Comparison")
        sections1 = {s.name: s.header for s in self.elf1.iter_sections()}
        sections2 = {s.name: s.header for s in self.elf2.iter_sections()}
        
        all_sections = sorted(list(set(sections1.keys()) | set(sections2.keys())))

        header_line = f"{'Name':<20} {'Type':<15} {'Address':<12} {'Size':<10}"
        self._add_content([header_line], [header_line])
        self._add_content(["-" * 60], ["-" * 60])

        for name in all_sections:
            s1 = sections1.get(name)
            s2 = sections2.get(name)
            
            line1_val = "Not Found"
            line2_val = "Not Found"
            tag1 = None
            tag2 = None

            if s1:
                line1_val = f"{name:<20} {s1.sh_type:<15} {hex(s1.sh_addr):<12} {s1.sh_size:<10}"
            if s2:
                line2_val = f"{name:<20} {s2.sh_type:<15} {hex(s2.sh_addr):<12} {s2.sh_size:<10}"

            if s1 and s2:
                if line1_val != line2_val:
                    tag1 = 'diff'
                    tag2 = 'diff'
            elif s1 and not s2:
                tag1 = 'deleted'
                tag2 = None
            elif not s1 and s2:
                tag1 = None
                tag2 = 'added'
            
            self._add_content([line1_val], [line2_val], tag1, tag2)
        print("[DEBUG] Section Header Comparison displayed.")

    def _display_symbol_comparison(self):
        print("[DEBUG] Displaying Symbol Table Comparison.")
        if not self.elf1 or not self.elf2:
            messagebox.showinfo("Info", "Please load both ELF files first.")
            return

        self._clear_texts()
        self._add_title("Symbol Table (.symtab) Comparison")
        
        # Now using symbols populated by readelf
        symbols1 = self.all_symbols1
        symbols2 = self.all_symbols2
        all_symbols = sorted(list(set(symbols1.keys()) | set(symbols2.keys())))

        if not symbols1 and not symbols2:
            self._add_content(["No symbols found via readelf -Ws."], ["No symbols found via readelf -Ws."])
            print("[DEBUG] No symbols found via readelf.")
            return

        header_line = f"{'Name':<30} {'Value':<12} {'Size':<8} {'Type':<10} {'Bind':<10}"
        self._add_content([header_line], [header_line])
        self._add_content(["-" * 75], ["-" * 75])

        for name in all_symbols:
            if not name: continue
            s1 = symbols1.get(name)
            s2 = symbols2.get(name)

            line1_val = "Not Found"
            line2_val = "Not Found"
            tag1 = None
            tag2 = None

            if s1:
                line1_val = f"{name:<30} {hex(s1['addr']):<12} {s1['size']:<8} {s1['type'].replace('STT_',''):<10} {s1['bind'].replace('STB_',''):<10}"
            if s2:
                line2_val = f"{name:<30} {hex(s2['addr']):<12} {s2['size']:<8} {s2['type'].replace('STT_',''):<10} {s2['bind'].replace('STB_',''):<10}"

            if s1 and s2:
                if (s1['addr'] != s2['addr'] or 
                    s1['size'] != s2['size'] or
                    s1['type'] != s2['type'] or
                    s1['bind'] != s2['bind']):
                    tag1 = 'diff'
                    tag2 = 'diff'
            elif s1 and not s2:
                tag1 = 'deleted'
                tag2 = None
            elif not s1 and s2:
                tag1 = None
                tag2 = 'added'
            
            self._add_content([line1_val], [line2_val], tag1, tag2)
        print("[DEBUG] Symbol Table Comparison displayed.")


    def _on_symbol_select(self, event):
        """Handler for when a symbol is selected in the listbox."""
        selected_indices = self.function_list.curselection()
        if not selected_indices:
            print("[DEBUG] No symbol selected in the listbox.")
            return

        selected_symbol_text = self.function_list.get(selected_indices[0])
        # Extract symbol name by removing the status and type suffix (e.g., "(Modified) (Func)")
        symbol_name = selected_symbol_text.split(" (")[0] 
        print(f"[DEBUG] Symbol selected: {symbol_name}")

        sym1_info = self.all_symbols1.get(symbol_name)
        sym2_info = self.all_symbols2.get(symbol_name)

        is_function1 = sym1_info and sym1_info['type'] == 'STT_FUNC'
        is_function2 = sym2_info and sym2_info['type'] == 'STT_FUNC'

        if is_function1 or is_function2:
            self._display_function_disassembly(symbol_name)
        else:
            self._clear_texts()
            self._add_title(f"Symbol Information: {symbol_name}")
            
            lines1 = []
            lines2 = []
            if sym1_info:
                lines1.append(f"Name: {symbol_name}")
                lines1.append(f"Value: 0x{sym1_info['addr']:x}")
                lines1.append(f"Size: {sym1_info['size']}")
                lines1.append(f"Type: {sym1_info['type'].replace('STT_','')}")
                lines1.append(f"Binding: {sym1_info['bind'].replace('STB_','')}")
                # Section index might be int or string, display appropriately
                section_idx_str = str(sym1_info['section_index']) if sym1_info['section_index'] is not None else "N/A"
                lines1.append(f"Section Index: {section_idx_str}")
            else:
                lines1.append(f"Symbol '{symbol_name}' not found in File 1.")

            if sym2_info:
                lines2.append(f"Name: {symbol_name}")
                lines2.append(f"Value: 0x{sym2_info['addr']:x}")
                lines2.append(f"Size: {sym2_info['size']}")
                lines2.append(f"Type: {sym2_info['type'].replace('STT_','')}")
                lines2.append(f"Binding: {sym2_info['bind'].replace('STB_','')}")
                section_idx_str = str(sym2_info['section_index']) if sym2_info['section_index'] is not None else "N/A"
                lines2.append(f"Section Index: {section_idx_str}")
            else:
                lines2.append(f"Symbol '{symbol_name}' not found in File 2.")
            
            self._add_content(lines1, lines2)
            messagebox.showinfo("Symbol Type", f"'{symbol_name}' is not a function (STT_FUNC) type.\nDisplaying symbol metadata instead.")
            print(f"[DEBUG] '{symbol_name}' is not a function. Displaying symbol info instead of disassembly.")

    def _disassemble_with_objdump(self, file_path, func_name, target_symbols):
        """
        Disassembles a specific function using objdump by obtaining its address and size
        from the provided target_symbols dictionary (which was populated by readelf).
        Uses -D option and improved output parsing.
        Returns a list of disassembly lines.
        """
        disassembly_lines = []
        objdump_cmd = self.objdump_path.get()
        if not objdump_cmd:
            return ["ERROR: objdump path is not set. Please configure it in 'External Tool Paths'."]
        
        func_info = target_symbols.get(func_name)

        if not func_info:
            return [f"Error: Function '{func_name}' not found in symbol table of '{os.path.basename(file_path)}' (based on readelf data)."]
        
        if func_info['type'] != 'STT_FUNC':
            return [f"Warning: '{func_name}' is not a function (STT_FUNC) type. Disassembly might not be meaningful. (Type: {func_info['type'].replace('STT_', '')})"]

        # Check if objdump exists and is executable
        if not os.path.exists(objdump_cmd) or not os.access(objdump_cmd, os.X_OK):
            if os.path.basename(objdump_cmd).lower() in ["objdump", "objdump.exe"]:
                 pass
            else:
                return [f"Error: The configured objdump path '{objdump_cmd}' is not a valid executable."]

        start_addr = func_info['addr']
        size = func_info['size']
        end_addr = start_addr + size

        if size == 0:
            return [f"Warning: Function '{func_name}' (Address 0x{start_addr:x}, Size 0 bytes) has a size of 0. No code to disassemble."]

        # Ensure addresses are passed as hexadecimal strings
        start_addr_hex = hex(start_addr)
        end_addr_hex = hex(end_addr)
        
        try:
            command = [
                objdump_cmd, 
                "-D",  # Use -D option
                "--start-address=" + start_addr_hex, 
                "--stop-address=" + end_addr_hex, 
                "--show-all-symbols", 
                # "--visualize-jumps", # Removed as requested
                file_path
            ]
            
            print(f"[DEBUG] Running objdump command for {func_name} (Addr: {start_addr_hex}-{end_addr_hex}):\n{' '.join(command)}")
            process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore', timeout=60) # Increased timeout
            output_lines = process.stdout.splitlines()

            final_disassembly = []
            capture_disasm = False
            
            # Function name as a pattern, robust to different objdump outputs
            func_pattern_label = f"<{func_name}>:" # Common pattern for function start label
            func_pattern_addr_start = f"{start_addr_hex.replace('0x', '')}:" # Address at start of line

            for line in output_lines:
                line_stripped = line.strip()

                # Start capturing when we hit the function's address or name label
                if not capture_disasm:
                    if func_pattern_label in line or line_stripped.startswith(func_pattern_addr_start):
                        capture_disasm = True
                        final_disassembly.append(line) # Include the starting label/address line
                        continue
                    continue # Skip lines before the target function

                # Once capturing, include lines that look like disassembly or relevant labels
                # Heuristic: looks like an address, then a tab, then possibly hex bytes, then mnemonic/opcodes
                # Or lines that are jump targets/labels
                is_disassembly_line = False
                if "\t" in line_stripped:
                    parts = line_stripped.split('\t')
                    if len(parts) >= 2:
                        try:
                            # Check if the first part (before first tab) looks like an address
                            # and the second part (after first tab) contains hex bytes, or is empty (for jump labels)
                            address_part = parts[0]
                            if address_part.startswith("0x"): # e.g., "0x12345:"
                                int(address_part, 16) # Just to check if it's a valid hex number
                                is_disassembly_line = True
                            elif ":" in address_part and len(address_part.split(':')[0]) <= 16 and all(c in '0123456789abcdefABCDEF' for c in address_part.split(':')[0].strip()):
                                # e.g., "   12345:" (without 0x prefix)
                                is_disassembly_line = True
                            elif address_part.endswith(":") and " " not in address_part: # Local labels like "00000000 <.L0>:"
                                is_disassembly_line = True
                        except ValueError:
                            pass
                
                # Heuristic: lines containing addresses or relative offsets in the middle, or local labels
                if is_disassembly_line or \
                   (line_stripped.startswith('0x') and ':' in line_stripped and '\t' in line_stripped) or \
                   (' <' in line and '>' in line and not line_stripped.startswith("file format")) or \
                   line_stripped.startswith("...") or \
                   (line_stripped.startswith("0x") and len(line_stripped.split(':')[0].strip()) > 4 and len(line_stripped.split('\t')) > 1): # Address followed by content

                    final_disassembly.append(line)
                    
                    # Stop capturing when we go past the function's expected end address
                    # This is a heuristic. It might cut off the last instruction if it aligns perfectly.
                    try:
                        line_addr_str = line_stripped.split(':')[0].strip()
                        current_line_addr = None
                        if line_addr_str.startswith("0x"):
                            current_line_addr = int(line_addr_str, 16)
                        elif len(line_addr_str) <= 16 and all(c in '0123456789abcdefABCDEF' for c in line_addr_str): # Address without 0x
                             current_line_addr = int(line_addr_str, 16)

                        if current_line_addr is not None and current_line_addr >= end_addr:
                            # To avoid stopping exactly on the end_addr if it's the start of an instruction
                            # we need to consider the size of the last instruction.
                            # Since we don't parse instruction size here, a simple >= check is a compromise.
                            # However, if the function is very small (e.g., size 1 byte),
                            # the `start_addr` might already be equal to or greater than `end_addr`.
                            # We should only break if we've processed at least one instruction that clearly starts beyond the function.
                            if current_line_addr > end_addr: # Stop if current line's address is strictly beyond the function end
                                # Or, if current_line_addr == end_addr AND we are sure it's not the start of the last instruction
                                # (which is hard to determine without Capstone here).
                                # For now, a strict `>` is safer than `>=`, which might cut off the last instruction.
                                break
                    except (ValueError, IndexError):
                        pass # Line doesn't start with a parseable address, continue
                else:
                    # If we are capturing, but the line doesn't look like disassembly, it might be a new section header
                    # or an unrelated comment that objdump sometimes adds, or a new function label.
                    # If it's a new function label and not related to our target function, stop capturing.
                    if "<" in line and ">" in line and func_name not in line and "file format" not in line and "Disassembly of section" not in line:
                         # This is a strong heuristic for a new function's start label
                         # E.g., "000000000004000 <new_function_name>:"
                        try:
                            addr_part = line.split('<')[0].strip()
                            if addr_part.startswith("0x") or all(c in '0123456789abcdefABCDEF' for c in addr_part):
                                next_func_addr = int(addr_part, 16)
                                if next_func_addr >= end_addr: # If the next function starts after our target, stop
                                     break
                        except ValueError:
                            pass
                    # Also, break if we encounter another "Disassembly of section" or "Contents of section" header
                    if "Disassembly of section" in line or "Contents of section" in line:
                        break # Stop capturing

            # Filter out objdump's preamble/postamble that might still be in the captured lines
            filtered_final_disassembly = []
            for line in final_disassembly:
                if line.strip().startswith(file_path) or \
                   "file format" in line.strip() or \
                   "Disassembly of section" in line.strip() or \
                   "Contents of section" in line.strip() or \
                   (line.strip().startswith("0x") and ":" not in line.strip() and len(line.strip().split()) == 1): # Single hex number line, not instruction
                    continue
                filtered_final_disassembly.append(line)

            # Final check for empty output after filtering
            if not filtered_final_disassembly and size > 0: # Only warn if func has size but no output
                return [f"Warning: objdump did not produce valid disassembly output for '{func_name}' (Address 0x{start_addr:x}, Size {size} bytes). This may indicate a non-executable section, zero size, or incorrect address range. Check raw objdump output."]
            
            return filtered_final_disassembly

        except FileNotFoundError:
            messagebox.showerror("Error", f"objdump command '{objdump_cmd}' not found.\nPlease ensure Binutils is installed and objdump is in your system PATH, or set the correct path in 'External Tool Paths'.")
            print(f"[DEBUG] objdump command '{objdump_cmd}' not found. Traceback:\n{traceback.format_exc()}")
            return [f"Error: objdump command '{objdump_cmd}' not found for '{func_name}'."]
        except subprocess.CalledProcessError as e:
            messagebox.showerror("objdump Error", f"objdump execution failed: {e.stderr}")
            print(f"[DEBUG] objdump execution failed. Error: {e.stderr}. Traceback:\n{traceback.format_exc()}")
            return [f"objdump execution error for '{func_name}': {e.stderr.strip()}"]
        except subprocess.TimeoutExpired:
            messagebox.showerror("objdump Error", f"objdump execution timed out. Disassembly for '{func_name}' took too long.")
            print(f"[DEBUG] objdump timeout for '{func_name}'. Traceback:\n{traceback.format_exc()}")
            return [f"Error: objdump execution timed out for '{func_name}'."]
        except Exception as e:
            print(f"[DEBUG] Unexpected error during objdump disassembly: {e}. Traceback:\n{traceback.format_exc()}")
            return [f"Error during objdump disassembly for '{func_name}': {type(e).__name__}: {e}"]

    def _display_function_disassembly(self, func_name):
        """Displays the disassembly for a given function name, using the selected method."""
        print(f"[DEBUG] Displaying disassembly for function: {func_name}")
        if not self.elf1 or not self.elf2:
            messagebox.showinfo("Info", "Please load both ELF files first.")
            print("[DEBUG] Cannot display disassembly: ELF files not loaded.")
            return

        self._clear_texts()
        self._add_title(f"Function Disassembly: {func_name}")

        func1_info = self.functions1.get(func_name) # These are populated by readelf
        func2_info = self.functions2.get(func_name) # These are populated by readelf

        disassembly1 = []
        disassembly2 = []
        selected_method = self.disassembly_method.get()
        print(f"[DEBUG] Disassembly method selected: {selected_method}")

        # --- File 1 Disassembly ---
        if func1_info:
            print(f"\n[DEBUG] --- File 1 Disassembly for {func_name} (Method: {selected_method}) ---")
            
            if selected_method == "Capstone (Internal)":
                # Capstone still relies on elftools' direct access to section data
                endian_mode1 = CS_MODE_LITTLE_ENDIAN if self.elf1.header['e_ident']['EI_DATA'] == 'ELFDATA2LSB' else CS_MODE_BIG_ENDIAN
                try:
                    # Need to get the section by index from elftools' parsed ELF
                    section = None
                    # Search by section name first, then by index if name is not found
                    if func1_info['section_index'] is not None:
                        # Attempt to get section name from elftools internal representation for section_index
                        sec_name_from_elftools = None
                        if isinstance(func1_info['section_index'], int) and func1_info['section_index'] < len(self.elf1.sections):
                            sec_name_from_elftools = self.elf1.get_section(func1_info['section_index']).name
                        elif isinstance(func1_info['section_index'], str): # If readelf provided a name directly (e.g., '.text')
                            sec_name_from_elftools = func1_info['section_index']

                        for sec in self.elf1.iter_sections():
                            if sec.name == sec_name_from_elftools:
                                section = sec
                                break
                        
                        if section is None and isinstance(func1_info['section_index'], int):
                            try: # Fallback to direct numeric index if name lookup fails
                                section = self.elf1.get_section(func1_info['section_index'])
                            except IndexError:
                                pass # Index out of bounds

                    if section:
                        if section['sh_type'] != 'SHT_PROGBITS' and section['sh_type'] != 'SHT_NOBITS': # SHT_NOBITS might be BSS for example
                            disassembly1.append(f"Warning: Section '{section.name}' (File 1) has type '{section['sh_type']}'. Capstone disassembles only 'SHT_PROGBITS' sections. (Required type for code)")
                            print(f"[DEBUG] WARNING (File 1): Section '{section.name}' is not PROGBITS. Type: {section['sh_type']}")
                            # For non-code sections, just show symbol info
                            disassembly1.append(f"Name: {func_name}")
                            disassembly1.append(f"Value: 0x{func1_info['addr']:x}")
                            disassembly1.append(f"Size: {func1_info['size']}")
                            disassembly1.append(f"Type: {func1_info['type'].replace('STT_','')}")
                            disassembly1.append(f"Binding: {func1_info['bind'].replace('STB_','')}")
                            disassembly1.append(f"Section Index: {str(func1_info['section_index'])}")
                            disassembly1.append("--------------------------------------")

                        elif func1_info['size'] == 0:
                            disassembly1.append(f"Warning: Function '{func_name}' (File 1) has a size of 0 bytes. No code to disassemble.")
                            print(f"[DEBUG] WARNING (File 1): Function '{func_name}' has 0 size.")
                        elif section.data() is None:
                             disassembly1.append(f"Error: Section '{section.name}' (File 1) has no data. Cannot disassemble.")
                             print(f"[DEBUG] ERROR (File 1): Section '{section.name}' has no data.")
                        else:
                            offset = func1_info['addr'] - section['sh_addr']
                            end_offset = offset + func1_info['size']

                            func_code = section.data()[max(0, offset) : min(len(section.data()), end_offset)]
                            
                            md_current = None
                            disasm_addr_actual = func1_info['addr']
                            
                            if self.arch_name1 == "ARM":
                                if (func1_info['addr'] & 1): # Check LSB for Thumb mode
                                    md_current = Cs(CS_ARCH_ARM, CS_MODE_THUMB | endian_mode1)
                                    disasm_addr_actual = func1_info['addr'] & ~1 # Clear LSB for Capstone
                                else:
                                    md_current = Cs(CS_ARCH_ARM, CS_MODE_ARM | endian_mode1)
                            else:
                                md_current = self.md1_base

                            if not md_current:
                                disassembly1.append(f"Error: Capstone disassembler for File 1 architecture '{self.arch_name1}' not initialized.")
                            elif not func_code:
                                disassembly1.append(f"Failed to extract executable code for '{func_name}' from File 1. (Extracted code length: {len(func_code)} bytes)")
                            else:
                                inst_count = 0
                                try:
                                    for i in md_current.disasm(func_code, disasm_addr_actual):
                                        disassembly1.append(f"0x{i.address:x}:\t{i.mnemonic}\t{i.op_str}")
                                        inst_count += 1
                                        if inst_count >= 500:
                                            disassembly1.append("Disassembly truncated (more than 500 instructions).")
                                            break
                                    if inst_count == 0 and len(func_code) > 0:
                                        disassembly1.append(f"Error: Capstone failed to generate instructions for {len(func_code)} bytes in File 1. This often indicates a mode/data mismatch.")
                                except Exception as capstone_e:
                                    disassembly1.append(f"Capstone disassembly error (File 1): {type(capstone_e).__name__}: {capstone_e}")
                                    print(f"[DEBUG] Capstone Error (File 1): {capstone_e}. Traceback:\n{traceback.format_exc()}")
                    else:
                        disassembly1.append(f"Error: Section for '{func_name}' not found in File 1. (Index: {func1_info['section_index']})")
                        print(f"[DEBUG] ERROR (File 1): Section not found for function.")

                except Exception as e:
                    disassembly1 = [f"Error during disassembly of function '{func_name}' in File 1 (Capstone): {type(e).__name__}: {e}"]
                    print(f"[DEBUG] Capstone general error (File 1): {e}. Traceback:\n{traceback.format_exc()}")
            
            elif selected_method == "objdump (External)":
                if not self.file1_path.get():
                    disassembly1.append("Error: File 1 path not set for objdump.")
                else:
                    # Pass the symbol dictionary to objdump disassembly
                    disassembly1 = self._disassemble_with_objdump(self.file1_path.get(), func_name, self.all_symbols1)

        else:
            disassembly1 = [f"Function '{func_name}' not found in File 1."]
            print(f"[DEBUG] Function '{func_name}' not in File 1's symbol table.")

        # --- File 2 Disassembly ---
        if func2_info:
            print(f"\n[DEBUG] --- File 2 Disassembly for {func_name} (Method: {selected_method}) ---")

            if selected_method == "Capstone (Internal)":
                endian_mode2 = CS_MODE_LITTLE_ENDIAN if self.elf2.header['e_ident']['EI_DATA'] == 'ELFDATA2LSB' else CS_MODE_BIG_ENDIAN
                try:
                    section = None
                    # Search by section name first, then by index if name is not found
                    if func2_info['section_index'] is not None:
                        sec_name_from_elftools = None
                        if isinstance(func2_info['section_index'], int) and func2_info['section_index'] < len(self.elf2.sections):
                            sec_name_from_elftools = self.elf2.get_section(func2_info['section_index']).name
                        elif isinstance(func2_info['section_index'], str):
                            sec_name_from_elftools = func2_info['section_index']

                        for sec in self.elf2.iter_sections():
                            if sec.name == sec_name_from_elftools:
                                section = sec
                                break
                        
                        if section is None and isinstance(func2_info['section_index'], int):
                            try:
                                section = self.elf2.get_section(func2_info['section_index'])
                            except IndexError:
                                pass

                    if section:
                        if section['sh_type'] != 'SHT_PROGBITS' and section['sh_type'] != 'SHT_NOBITS':
                            disassembly2.append(f"Warning: Section '{section.name}' (File 2) has type '{section['sh_type']}'. Capstone disassembles only 'SHT_PROGBITS' sections. (Required type for code)")
                            print(f"[DEBUG] WARNING (File 2): Section '{section.name}' is not PROGBITS. Type: {section['sh_type']}")
                            # For non-code sections, just show symbol info
                            disassembly2.append(f"Name: {func_name}")
                            disassembly2.append(f"Value: 0x{func2_info['addr']:x}")
                            disassembly2.append(f"Size: {func2_info['size']}")
                            disassembly2.append(f"Type: {func2_info['type'].replace('STT_','')}")
                            disassembly2.append(f"Binding: {func2_info['bind'].replace('STB_','')}")
                            disassembly2.append(f"Section Index: {str(func2_info['section_index'])}")
                            disassembly2.append("--------------------------------------")

                        elif func2_info['size'] == 0:
                            disassembly2.append(f"Warning: Function '{func_name}' (File 2) has a size of 0 bytes. No code to disassemble.")
                            print(f"[DEBUG] WARNING (File 2): Function '{func_name}' has 0 size.")
                        elif section.data() is None:
                            disassembly2.append(f"Error: Section '{section.name}' (File 2) has no data. Cannot disassemble.")
                            print(f"[DEBUG] ERROR (File 2): Section '{section.name}' has no data.")
                        else:
                            offset = func2_info['addr'] - section['sh_addr']
                            end_offset = offset + func2_info['size']

                            func_code = section.data()[max(0, offset) : min(len(section.data()), end_offset)]
                            
                            md_current = None
                            disasm_addr_actual = func2_info['addr']
                            if self.arch_name2 == "ARM":
                                if (func2_info['addr'] & 1):
                                    md_current = Cs(CS_ARCH_ARM, CS_MODE_THUMB | endian_mode2)
                                    disasm_addr_actual = func2_info['addr'] & ~1
                                else:
                                    md_current = Cs(CS_ARCH_ARM, CS_MODE_ARM | endian_mode2)
                            else:
                                md_current = self.md2_base

                            if not md_current:
                                disassembly2.append(f"Error: Capstone disassembler for File 2 architecture '{self.arch_name2}' not initialized.")
                            elif not func_code:
                                disassembly2.append(f"Failed to extract executable code for '{func_name}' from File 2. (Extracted code length: {len(func_code)} bytes)")
                            else:
                                inst_count = 0
                                try:
                                    for i in md_current.disasm(func_code, disasm_addr_actual):
                                        disassembly2.append(f"0x{i.address:x}:\t{i.mnemonic}\t{i.op_str}")
                                        inst_count += 1
                                        if inst_count >= 500:
                                            disassembly2.append("Disassembly truncated (more than 500 instructions).")
                                            break
                                    if inst_count == 0 and len(func_code) > 0:
                                        disassembly2.append(f"Error: Capstone failed to generate instructions for {len(func_code)} bytes in File 2. This often indicates a mode/data mismatch.")
                                except Exception as capstone_e:
                                    disassembly2.append(f"Capstone disassembly error (File 2): {type(capstone_e).__name__}: {capstone_e}")
                                    print(f"[DEBUG] Capstone Error (File 2): {capstone_e}. Traceback:\n{traceback.format_exc()}")
                    else:
                        disassembly2.append(f"Error: Section for '{func_name}' not found in File 2. (Index: {func2_info['section_index']})")
                        print(f"[DEBUG] ERROR (File 2): Section not found for function.")

                except Exception as e:
                    disassembly2 = [f"Error during disassembly of function '{func_name}' in File 2 (Capstone): {type(e).__name__}: {e}"]
                    print(f"[DEBUG] Capstone general error (File 2): {e}. Traceback:\n{traceback.format_exc()}")
            
            elif selected_method == "objdump (External)":
                if not self.file2_path.get():
                    disassembly2.append("Error: File 2 path not set for objdump.")
                else:
                    # Pass the symbol dictionary to objdump disassembly
                    disassembly2 = self._disassemble_with_objdump(self.file2_path.get(), func_name, self.all_symbols2)
        else:
            disassembly2 = [f"Function '{func_name}' not found in File 2."]
            print(f"[DEBUG] Function '{func_name}' not in File 2's symbol table.")

        print("[DEBUG] Performing diff on disassembled functions.")
        d = difflib.SequenceMatcher(None, disassembly1, disassembly2)
        
        self.text1.config(state=tk.NORMAL)
        self.text2.config(state=tk.NORMAL)
        self.text1.delete('1.0', tk.END)
        self.text2.delete('1.0', tk.END)

        for tag, i1, i2, j1, j2 in d.get_opcodes():
            lines1_segment = disassembly1[i1:i2]
            lines2_segment = disassembly2[j1:j2]

            if tag == 'equal':
                self._add_content(lines1_segment, lines2_segment)
            elif tag == 'delete':
                self._add_content(lines1_segment, [""] * len(lines1_segment), tag1='deleted', tag2=None)
            elif tag == 'insert':
                self._add_content([""] * len(lines2_segment), lines2_segment, tag1=None, tag2='added')
            elif tag == 'replace':
                nested_d = difflib.SequenceMatcher(None, lines1_segment, lines2_segment)
                for nested_tag, ni1, ni2, nj1, nj2 in nested_d.get_opcodes():
                    n_lines1 = lines1_segment[ni1:ni2]
                    n_lines2 = lines2_segment[nj1:nj2]

                    if nested_tag == 'equal':
                        self._add_content(n_lines1, n_lines2)
                    elif nested_tag == 'delete':
                        self._add_content(n_lines1, [""] * len(n_lines1), tag1='diff', tag2=None)
                    elif nested_tag == 'insert':
                        self._add_content([""] * len(n_lines2), n_lines2, tag1=None, tag2='diff')
                    elif nested_tag == 'replace':
                        self._add_content(n_lines1, n_lines2, tag1='diff', tag2='diff')
        
        self.text1.config(state=tk.DISABLED)
        self.text2.config(state=tk.DISABLED)
        print(f"[DEBUG] Disassembly for '{func_name}' displayed.")

    def _display_compilation_options_comparison(self):
        """
        Attempts to extract and compare compilation options from .debug_info section (DWARF).
        This uses elftools' DWARF parsing capabilities.
        """
        print("[DEBUG] Displaying Compilation Options Comparison.")
        if not self.elf1 or not self.elf2:
            messagebox.showinfo("Info", "Please load both ELF files first.")
            return

        self._clear_texts()
        self._add_title("Compilation Options Comparison (DWARF)")

        options1 = self._extract_compilation_options(self.elf1)
        options2 = self._extract_compilation_options(self.elf2)

        if not options1 and not options2:
            self._add_content(
                ["No DWARF .debug_info section or compilation unit information found."],
                ["No DWARF .debug_info section or compilation unit information found."]
            )
            print("[DEBUG] No DWARF info for compilation options comparison.")
            return

        all_keys = sorted(list(set(options1.keys()) | set(options2.keys())))
        
        lines1 = []
        lines2 = []
        tags1 = []
        tags2 = []

        for key in all_keys:
            val1 = options1.get(key, "N/A")
            val2 = options2.get(key, "N/A")

            line1 = f"{key:<25}: {val1}"
            line2 = f"{key:<25}: {val2}"
            lines1.append(line1)
            lines2.append(line2)

            if val1 != val2:
                tags1.append('diff')
                tags2.append('diff')
            else:
                tags1.append(None)
                tags2.append(None)
        
        for i in range(len(lines1)):
            self._add_content([lines1[i]], [lines2[i]], tags1[i], tags2[i])
        print("[DEBUG] Compilation Options Comparison displayed.")


    def _extract_compilation_options(self, elf):
        """
        Extracts compilation options from the DWARF debug info section using elftools.
        Focuses on DW_TAG_compile_unit DIEs.
        """
        options = {}
        if not elf.has_dwarf_info():
            print("[DEBUG] No DWARF info found in ELF file for compilation options.")
            return options

        try:
            dwarf_info = elf.get_dwarf_info()
            for CU in dwarf_info.iter_CUs():
                top_DIE = CU.get_top_DIE()
                if top_DIE.tag == 'DW_TAG_compile_unit':
                    if 'DW_AT_producer' in top_DIE.attributes:
                        options['Producer'] = top_DIE.attributes['DW_AT_producer'].value.decode('utf-8')
                    if 'DW_AT_comp_dir' in top_DIE.attributes:
                        options['Compilation Directory'] = top_DIE.attributes['DW_AT_comp_dir'].value.decode('utf-8')
                    if 'DW_AT_low_pc' in top_DIE.attributes:
                        options['Low PC'] = hex(top_DIE.attributes['DW_AT_low_pc'].value)
                    if 'DW_AT_high_pc' in top_DIE.attributes:
                        high_pc = top_DIE.attributes['DW_AT_high_pc']
                        if high_pc.form == 'DW_FORM_addr':
                            options['High PC'] = hex(high_pc.value)
                        elif high_pc.form == 'DW_FORM_data4' or high_pc.form == 'DW_FORM_data8':
                            options['Code Length'] = f"{high_pc.value} bytes"
                    
                    # More robust parsing for common compiler options from producer string
                    producer_str = options.get('Producer', '')
                    if producer_str:
                        # Optimization Level
                        if '-O0' in producer_str: options['Optimization Level'] = 'O0'
                        elif '-O1' in producer_str: options['Optimization Level'] = 'O1'
                        elif '-O2' in producer_str: options['Optimization Level'] = 'O2'
                        elif '-O3' in producer_str: options['Optimization Level'] = 'O3'
                        elif '-Os' in producer_str: options['Optimization Level'] = 'Os'
                        
                        # Debug Info
                        if '-g' in producer_str: options['Debug Info'] = 'Enabled'
                        else: 
                            # Check DW_AT_stmt_list / DW_AT_line_info
                            if 'DW_AT_stmt_list' in top_DIE.attributes or 'DW_AT_line_info' in top_DIE.attributes:
                                options['Debug Info'] = 'Enabled (implicit by line info)'
                            else:
                                options['Debug Info'] = 'Disabled (might be implicit)'
                        
                        # Position Independent Code/Executable
                        if '-fPIC' in producer_str: options['Position Independent Code'] = 'Enabled'
                        elif '-fPIE' in producer_str: options['Position Independent Executable'] = 'Enabled'

                        # C/C++ Standard
                        std_match = [s for s in producer_str.split() if s.startswith('-std=')]
                        if std_match: options['C/C++ Standard'] = std_match[0].split('=')[1]

                        # Architecture specific flags (basic examples)
                        if any(flag in producer_str for flag in ['-march=', '-mtune=']):
                            options['Arch Flags'] = 'Present'
                        if '-mfloat-abi=' in producer_str:
                            options['Floating Point ABI'] = [s for s in producer_str.split() if s.startswith('-mfloat-abi=')][0].split('=')[1]

                    break # Usually one main compile unit for compilation options
        except Exception as e:
            print(f"[DEBUG] Error extracting DWARF compilation options: {e}. Traceback:\n{traceback.format_exc()}")
            options['Error'] = f"Could not extract DWARF info: {e}"

        return options


# Main execution
if __name__ == "__main__":
    file1_path_arg = None
    file2_path_arg = None

    if len(sys.argv) >= 3:
        file1_path_arg = sys.argv[1]
        file2_path_arg = sys.argv[2]
        print(f"[DEBUG] Received command line arguments: File 1='{file1_path_arg}', File 2='{file2_path_arg}'")
    else:
        print("[DEBUG] No command line arguments for file paths found. Please select files via GUI or provide paths.")
        print("Usage: python your_script_name.py <file1_path> <file2_path>")

    print("[DEBUG] Application started.")
    root = tk.Tk()
    app = ELFComparerApp(root, file1=file1_path_arg, file2=file2_path_arg)
    root.mainloop()
    print("[DEBUG] Application closed.")
    