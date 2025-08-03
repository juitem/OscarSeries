import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, OptionMenu
import os
import sys
import re # Import regular expression module
import subprocess # Import subprocess module for running shell commands
import tkinter.colorchooser # Import colorchooser for color picker
from PIL import ImageGrab, Image # Import ImageGrab for screenshots, Image for saving

class FileViewerApp:
    def __init__(self, master):
        """
        Initializes the FileViewerApp.
        Args:
            master (tk.Tk): The root Tkinter window.
        """
        self.master = master
        master.title("TwinActionViewer") # Changed application title
        master.geometry("1400x850") # Set initial window size, wider and taller for new elements
        master.resizable(True, True) # Allow window resizing
        master.configure(bg="#F0F4F8") # Set a light, cool gray background for the main window

        self.file_path1 = None # Stores the actual path for File 1
        self.file_path2 = None # Stores the actual path for File 2

        # Toggle states
        self.show_percentage_changes = tk.BooleanVar(value=False)
        self.apply_colors_active = tk.BooleanVar(value=False)

        # Stored content for File 2
        self.original_content2 = ""
        self.percentage_formatted_content2 = ""
        self.percentage_data_for_coloring = [] # Stores (start_index, end_index, percentage_value) for coloring

        # Default color map for percentage changes
        # -100 to 0 (red shades), 0 (neutral), 0 to 100+ (blue shades)
        self.default_color_map_data = [
            (-100, "#B71C1C"),  # Darkest Red
            (-80, "#D32F2F"),   # Dark Red
            (-60, "#F44336"),   # Red
            (-40, "#FF7043"),   # Orange Red
            (-20, "#FFAB91"),   # Light Orange Red
            (0, "#424242"),     # Dark Gray (for 0%)
            (20, "#BBDEFB"),    # Very Light Blue
            (40, "#90CAF9"),    # Light Blue
            (60, "#64B5F6"),    # Medium Blue
            (80, "#42A5F5"),    # Blue
            (100, "#2196F3"),   # Dark Blue
            (float('inf'), "#1976D2") # Even Darker Blue (for >100% or infinite)
        ]

        # --- Top Control Bar ---
        self.top_control_bar = tk.Frame(master, padx=15, pady=10, bg="#E3F2FD", bd=2, relief=tk.RAISED) # Light blue background
        self.top_control_bar.pack(side=tk.TOP, fill=tk.X, pady=(10, 10), padx=10)

        # Command Input Row (Row 1)
        self.command_row_frame = tk.Frame(self.top_control_bar, bg="#E3F2FD")
        self.command_row_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        tk.Label(self.command_row_frame, text="Command:", bg="#E3F2FD", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        self.command_var = tk.StringVar(value="echo Full Path: %P, Basename: %F")
        self.entry_command = tk.Entry(self.command_row_frame, textvariable=self.command_var, width=60, bd=2, relief=tk.SUNKEN)
        self.entry_command.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.entry_command.bind('<Return>', self.execute_command)
        self.button_execute_command = tk.Button(self.command_row_frame, text="Execute", command=self.execute_command,
                                                bg="#66BB6A", fg="white", font=("Arial", 10, "bold"), bd=2, relief=tk.RAISED) # Softer green
        self.button_execute_command.pack(side=tk.LEFT, padx=(0, 0))

        # Options Row (Regex, %, Save as HTML, Font Size) (Row 2)
        self.options_row_frame = tk.Frame(self.top_control_bar, bg="#E3F2FD")
        self.options_row_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))

        tk.Label(self.options_row_frame, text="Exclude Lines (Regex):", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.exclude_lines_regex_var = tk.StringVar(value="")
        self.entry_exclude_lines_regex = tk.Entry(self.options_row_frame, textvariable=self.exclude_lines_regex_var, width=20, bd=2, relief=tk.SUNKEN)
        self.entry_exclude_lines_regex.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(self.options_row_frame, text="Exclude Words (Regex):", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.exclude_words_regex_var = tk.StringVar(value="")
        self.entry_exclude_words_regex = tk.Entry(self.options_row_frame, textvariable=self.exclude_words_regex_var, width=20, bd=2, relief=tk.SUNKEN)
        self.entry_exclude_words_regex.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(self.options_row_frame, text="Font Size:", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.font_sizes = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24]
        self.selected_font_size = tk.IntVar(value=10)
        self.font_size_option_menu = OptionMenu(self.options_row_frame, self.selected_font_size, *self.font_sizes, command=self.update_font_size)
        self.font_size_option_menu.config(bg="#BBDEFB", bd=1, relief=tk.RAISED) # Lighter blue for OptionMenu
        self.font_size_option_menu.pack(side=tk.LEFT, padx=(0, 15))

        # Modified % button to toggle
        self.button_percentage = tk.Button(self.options_row_frame, text="%", command=self.toggle_percentage_display,
                                            bg="#42A5F5", fg="white", font=("Arial", 10, "bold"), bd=2, relief=tk.RAISED) # Softer blue
        self.button_percentage.pack(side=tk.LEFT, padx=5)

        # Modified Apply Colors button to toggle
        self.button_apply_colors = tk.Button(self.options_row_frame, text="Apply Colors", command=self.toggle_apply_colors,
                                             bg="#607D8B", fg="white", font=("Arial", 10, "bold"), bd=2, relief=tk.RAISED) # Blue-gray
        self.button_apply_colors.pack(side=tk.LEFT, padx=5)

        self.button_save_html = tk.Button(self.options_row_frame, text="Save as HTML", command=self.save_as_html,
                                           bg="#FFCA28", fg="black", font=("Arial", 10, "bold"), bd=2, relief=tk.RAISED) # Softer amber
        self.button_save_html.pack(side=tk.LEFT, padx=5)

        # New: Save as JPEG button
        self.button_save_jpeg = tk.Button(self.options_row_frame, text="Save as JPEG", command=self.save_as_jpeg,
                                           bg="#795548", fg="white", font=("Arial", 10, "bold"), bd=2, relief=tk.RAISED) # Brown
        self.button_save_jpeg.pack(side=tk.LEFT, padx=5)


        # Custom Placeholders Row (Row 3)
        self.placeholder_row_frame = tk.Frame(self.top_control_bar, bg="#E3F2FD")
        self.placeholder_row_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

        tk.Label(self.placeholder_row_frame, text="File 1 %U:", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 2))
        self.u_var1 = tk.StringVar(value="")
        self.entry_u1 = tk.Entry(self.placeholder_row_frame, textvariable=self.u_var1, width=10, bd=1, relief=tk.SUNKEN)
        self.entry_u1.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(self.placeholder_row_frame, text="File 1 %K:", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 2))
        self.k_var1 = tk.StringVar(value="")
        self.entry_k1 = tk.Entry(self.placeholder_row_frame, textvariable=self.k_var1, width=10, bd=1, relief=tk.SUNKEN)
        self.entry_k1.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(self.placeholder_row_frame, text="File 2 %U:", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 2))
        self.u_var2 = tk.StringVar(value="")
        self.entry_u2 = tk.Entry(self.placeholder_row_frame, textvariable=self.u_var2, width=10, bd=1, relief=tk.SUNKEN)
        self.entry_u2.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(self.placeholder_row_frame, text="File 2 %K:", bg="#E3F2FD", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 2))
        self.k_var2 = tk.StringVar(value="")
        self.entry_k2 = tk.Entry(self.placeholder_row_frame, textvariable=self.k_var2, width=10, bd=1, relief=tk.SUNKEN)
        self.entry_k2.pack(side=tk.LEFT, padx=(0, 0))

        # --- Percentage Color Map Configuration (New Section) ---
        self.color_map_frame = tk.LabelFrame(self.top_control_bar, text="Percentage Color Map", padx=10, pady=5, bg="#E3F2FD", bd=2, relief=tk.GROOVE)
        self.color_map_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

        # Removed Add Color Rule Button

        # Frame to hold horizontal color map entries
        self.color_map_entries_container = tk.Frame(self.color_map_frame, bg="#E3F2FD")
        self.color_map_entries_container.pack(fill=tk.BOTH, expand=True)

        self.color_map_entries = [] # List to hold (threshold_var, color_hex_var, row_frame, color_display_button, range_label) tuples

        # Initialize with default color map entries
        self._initialize_default_color_map_ui()


        # --- Main Content PanedWindow (replaces main_content_frame) ---
        # Use PanedWindow for resizable divider
        self.paned_window = tk.PanedWindow(master, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, bd=2, bg="#F0F4F8") # Main window bg
        self.paned_window.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Frame for File 1 ---
        self.frame1 = tk.LabelFrame(self.paned_window, text="File 1 Content", padx=10, pady=10, bg="#FFFFFF", bd=2, relief=tk.GROOVE)
        self.paned_window.add(self.frame1) # Add to PanedWindow
        # self.paned_window.paneconfigure(self.frame1, weight=1) # Removed weight option due to potential TclError

        # Input Frame for File 1 (Browse Button + Entry + Reload Button)
        self.file_input_frame1 = tk.Frame(self.frame1, bg="#FFFFFF")
        self.file_input_frame1.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))

        self.button_browse1 = tk.Button(self.file_input_frame1, text="Browse", command=lambda: self.browse_file(1),
                                        bg="#78909C", fg="white", font=("Arial", 9), bd=2, relief=tk.RAISED) # Softer blue gray
        self.button_browse1.pack(side=tk.LEFT, padx=(0, 5))

        self.file_path_var1 = tk.StringVar(value="Enter file path or browse...")
        self.entry_file1 = tk.Entry(self.file_input_frame1, textvariable=self.file_path_var1, width=60, bd=2, relief=tk.SUNKEN)
        self.entry_file1.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry_file1.bind('<Return>', lambda event: self.load_file_from_entry(1))

        self.button_reload1 = tk.Button(self.file_input_frame1, text="Reload", command=lambda: self.reload_file(1),
                                        bg="#B0BEC5", fg="black", font=("Arial", 9), bd=2, relief=tk.RAISED) # Grayish for reload
        self.button_reload1.pack(side=tk.LEFT, padx=(5, 0))


        self.text_area1 = scrolledtext.ScrolledText(self.frame1, wrap=tk.WORD, width=50, height=20, font=("Consolas", self.selected_font_size.get()), bd=2, relief=tk.SUNKEN)
        self.text_area1.pack(fill=tk.BOTH, expand=True, pady=(5,0))


        # --- Frame for File 2 ---
        self.frame2 = tk.LabelFrame(self.paned_window, text="File 2 Content", padx=10, pady=10, bg="#FFFFFF", bd=2, relief=tk.GROOVE)
        self.paned_window.add(self.frame2) # Add to PanedWindow
        # self.paned_window.paneconfigure(self.frame2, weight=1) # Removed weight option due to potential TclError

        # Input Frame for File 2 (Browse Button + Entry + Reload Button)
        self.file_input_frame2 = tk.Frame(self.frame2, bg="#FFFFFF")
        self.file_input_frame2.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))

        self.button_browse2 = tk.Button(self.file_input_frame2, text="Browse", command=lambda: self.browse_file(2),
                                        bg="#78909C", fg="white", font=("Arial", 9), bd=2, relief=tk.RAISED) # Softer blue gray
        self.button_browse2.pack(side=tk.LEFT, padx=(0, 5))

        self.file_path_var2 = tk.StringVar(value="Enter file path or browse...")
        self.entry_file2 = tk.Entry(self.file_input_frame2, textvariable=self.file_path_var2, width=60, bd=2, relief=tk.SUNKEN)
        self.entry_file2.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry_file2.bind('<Return>', lambda event: self.load_file_from_entry(2))

        self.button_reload2 = tk.Button(self.file_input_frame2, text="Reload", command=lambda: self.reload_file(2),
                                        bg="#B0BEC5", fg="black", font=("Arial", 9), bd=2, relief=tk.RAISED) # Grayish for reload
        self.button_reload2.pack(side=tk.LEFT, padx=(5, 0))

        self.text_area2 = scrolledtext.ScrolledText(self.frame2, wrap=tk.WORD, width=50, height=20, font=("Consolas", self.selected_font_size.get()), bd=2, relief=tk.SUNKEN)
        self.text_area2.pack(fill=tk.BOTH, expand=True, pady=(5,0))

        # Check for command-line arguments
        if len(sys.argv) == 3:
            self.load_files_from_args(sys.argv[1], sys.argv[2])
        elif len(sys.argv) > 1:
            messagebox.showwarning("Warning", "Please provide exactly two file paths as arguments, or no arguments to use the GUI.")

    def _initialize_default_color_map_ui(self):
        """
        Initializes the color map UI with default entries.
        """
        for thresh, color in self.default_color_map_data:
            self.add_color_map_entry(initial_threshold=str(thresh), initial_color=color)
        self._update_color_map_range_labels() # Initial update of labels

    def add_color_map_entry(self, initial_threshold="", initial_color=""):
        """
        Adds a new set of widgets for a color map entry (range label, threshold, color picker)
        and packs them horizontally into the container.
        """
        rule_frame = tk.Frame(self.color_map_entries_container, bg="#E3F2FD", bd=1, relief=tk.SUNKEN)
        rule_frame.pack(side=tk.LEFT, padx=2, pady=1) # Pack horizontally with small padding

        range_label = tk.Label(rule_frame, text="", bg="#E3F2FD", font=("Arial", 8))
        range_label.pack(side=tk.LEFT, padx=(0, 2)) # Combined range label

        thresh_var = tk.StringVar(value=initial_threshold)
        color_hex_var = tk.StringVar(value=initial_color)

        entry_thresh = tk.Entry(rule_frame, textvariable=thresh_var, width=4, bd=1, relief=tk.SUNKEN, font=("Arial", 8)) # Adjusted width
        entry_thresh.pack(side=tk.LEFT, padx=(0, 2))
        # Bind KeyRelease to update labels AND trigger display update
        entry_thresh.bind("<KeyRelease>", lambda event: (self._update_color_map_range_labels(), self._update_display_content_and_colors()))

        color_display_button = tk.Button(rule_frame, text="", width=1, height=1,
                                         command=lambda: self.pick_color(color_hex_var, color_display_button),
                                         bg=initial_color if initial_color else "#FFFFFF", bd=1, relief=tk.RAISED)
        color_display_button.pack(side=tk.LEFT, padx=(0, 2))

        self.color_map_entries.append((thresh_var, color_hex_var, rule_frame, color_display_button, range_label)) # Store rule_frame and labels
        self._update_color_map_range_labels() # Update labels after adding new entry

    def remove_color_map_entry(self, rule_frame, thresh_var, color_hex_var, color_display_button, range_label):
        """
        Removes a color map entry rule_frame from the UI and internal list.
        This method is now a placeholder as the "X" button is removed.
        """
        messagebox.showinfo("Info", "Color rules can only be modified in the default settings.")

    def _update_color_map_range_labels(self):
        """
        Updates the min/max range labels for all color map entries based on their sorted thresholds.
        """
        sortable_entries = []
        for i, (thresh_var, _, _, _, _) in enumerate(self.color_map_entries):
            try:
                threshold_str = thresh_var.get().strip()
                if threshold_str.lower() == 'inf':
                    threshold = float('inf')
                elif threshold_str.lower() == '-inf':
                    threshold = float('-inf')
                else:
                    threshold = float(threshold_str)
                sortable_entries.append((threshold, i))
            except ValueError:
                sortable_entries.append((float('inf'), i))

        sortable_entries.sort(key=lambda x: x[0])

        for i in range(len(sortable_entries)):
            current_threshold_val, original_index = sortable_entries[i]
            _, _, _, _, range_label = self.color_map_entries[original_index]

            min_bound_str = ""
            if i == 0:
                min_bound_str = "-inf"
            else:
                prev_threshold_val = sortable_entries[i-1][0]
                min_bound_str = f"{prev_threshold_val:.0f}" if prev_threshold_val != float('-inf') else "-inf"
            
            max_bound_str = f"{current_threshold_val:.0f}" if current_threshold_val != float('inf') else "inf"

            range_label.config(text=f"{min_bound_str}~{max_bound_str}")

    def pick_color(self, color_hex_var, color_button):
        """
        Opens a color picker dialog and updates the color hex variable and button background.
        """
        color_code = tkinter.colorchooser.askcolor(title="Choose color")[1]
        if color_code:
            color_hex_var.set(color_code)
            color_button.config(bg=color_code)
            # After picking a color, trigger display update
            self._update_display_content_and_colors()

    def update_font_size(self, new_size):
        """
        Updates the font size of both text areas.
        Args:
            new_size (int): The new font size.
        """
        self.text_area1.config(font=("Consolas", new_size))
        self.text_area2.config(font=("Consolas", new_size))

    def browse_file(self, file_number):
        """
        Opens a file dialog to select a file and displays its content.
        Args:
            file_number (int): 1 for File 1, 2 for File 2.
        """
        file_path = filedialog.askopenfilename(
            title=f"Select File {file_number}",
            filetypes=[("All files", "*.*"), ("Text files", "*.txt"), ("Python files", "*.py")]
        )
        if file_path:
            if file_number == 1:
                self.file_path1 = file_path
                self.file_path_var1.set(file_path) # Update entry field
                self.display_file_content(self.file_path1, self.text_area1)
            elif file_number == 2:
                self.file_path2 = file_path
                self.file_path_var2.set(file_path) # Update entry field
                # Store original content and then update display
                try:
                    with open(self.file_path2, 'r', encoding='utf-8') as f:
                        self.original_content2 = f.read()
                    self.calculate_and_prepare_percentage_content() # Prepare percentage content
                    self._update_display_content_and_colors() # Update display based on toggles
                except Exception as e:
                    messagebox.showerror("Error", f"Error reading file {self.file_path2}: {e}")
                    self.text_area2.delete(1.0, tk.END)
                    self.text_area2.insert(tk.END, f"Error reading file: {e}")
                    self.file_path_var2.set("")


    def load_file_from_entry(self, file_number):
        """
        Loads a file based on the path entered in the Entry widget.
        Args:
            file_number (int): 1 for File 1, 2 for File 2.
        """
        if file_number == 1:
            file_path = self.file_path_var1.get()
            self.file_path1 = file_path # Update instance variable
            text_widget = self.text_area1
            self.display_file_content(file_path, text_widget)
        elif file_number == 2:
            file_path = self.file_path_var2.get()
            self.file_path2 = file_path # Update instance variable
            try:
                with open(self.file_path2, 'r', encoding='utf-8') as f:
                    self.original_content2 = f.read()
                self.calculate_and_prepare_percentage_content() # Prepare percentage content
                self._update_display_content_and_colors() # Update display based on toggles
            except FileNotFoundError:
                messagebox.showerror("Error", f"File not found: {file_path}")
                self.text_area2.delete(1.0, tk.END)
                self.text_area2.insert(tk.END, f"Error: File not found at '{file_path}'")
                self.file_path_var2.set("")
            except Exception as e:
                messagebox.showerror("Error", f"Error reading file {file_path}: {e}")
                self.text_area2.delete(1.0, tk.END)
                self.text_area2.insert(tk.END, f"Error reading file: {e}")
                self.file_path_var2.set("")

    def display_file_content(self, file_path, text_widget):
        """
        Reads content from a given file path and updates the specified text widget.
        This is primarily for File 1, as File 2's display is managed by _update_display_content_and_colors.
        Args:
            file_path (str): The path to the file.
            text_widget (tk.scrolledtext.ScrolledText): The text widget to update.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            text_widget.delete(1.0, tk.END) # Clear existing content
            text_widget.insert(tk.END, content) # Insert new content
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {file_path}")
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, f"Error: File not found at '{file_path}'")
            if text_widget == self.text_area1:
                self.file_path_var1.set("")
        except Exception as e:
            messagebox.showerror("Error", f"Error reading file {file_path}: {e}")
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, f"Error reading file: {e}")
            if text_widget == self.text_area1:
                self.file_path_var1.set("")

    def load_files_from_args(self, path1, path2):
        """
        Loads files directly from command-line arguments.
        Args:
            path1 (str): Path to the first file.
            path2 (str): Path to the second file.
        """
        self.file_path1 = path1
        self.file_path2 = path2
        self.file_path_var1.set(path1) # Update entry field
        self.file_path_var2.set(path2) # Update entry field
        
        # Load content for file1
        self.display_file_content(self.file_path1, self.text_area1)

        # Load content for file2, calculate percentages, and update display
        try:
            with open(self.file_path2, 'r', encoding='utf-8') as f:
                self.original_content2 = f.read()
            self.calculate_and_prepare_percentage_content()
            self._update_display_content_and_colors()
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {self.file_path2}")
            self.text_area2.delete(1.0, tk.END)
            self.text_area2.insert(tk.END, f"Error: File not found at '{self.file_path2}'")
            self.file_path_var2.set("")
        except Exception as e:
            messagebox.showerror("Error", f"Error reading file {self.file_path2}: {e}")
            self.text_area2.delete(1.0, tk.END)
            self.text_area2.insert(tk.END, f"Error reading file: {e}")
            self.file_path_var2.set("")


    def reload_file(self, file_number):
        """
        Reloads the content of a specific file if its path is set.
        Args:
            file_number (int): 1 for File 1, 2 for File 2.
        """
        if file_number == 1:
            if self.file_path1:
                self.display_file_content(self.file_path1, self.text_area1)
            else:
                messagebox.showinfo("Info", "File 1 path is not set. Please browse or enter a file path.")
        elif file_number == 2:
            if self.file_path2:
                # Reload original content and re-calculate percentages
                try:
                    with open(self.file_path2, 'r', encoding='utf-8') as f:
                        self.original_content2 = f.read()
                    self.calculate_and_prepare_percentage_content()
                    self._update_display_content_and_colors()
                except FileNotFoundError:
                    messagebox.showerror("Error", f"File not found: {self.file_path2}")
                    self.text_area2.delete(1.0, tk.END)
                    self.text_area2.insert(tk.END, f"Error: File not found at '{self.file_path2}'")
                    self.file_path_var2.set("")
                except Exception as e:
                    messagebox.showerror("Error", f"Error reading file {self.file_path2}: {e}")
                    self.text_area2.delete(1.0, tk.END)
                    self.text_area2.insert(tk.END, f"Error reading file: {e}")
                    self.file_path_var2.set("")
            else:
                messagebox.showinfo("Info", "File 2 path is not set. Please browse or enter a file path.")

    def _parse_color_map(self):
        """
        Parses the color map entries from the UI into a sorted list of (threshold, hex_color) tuples.
        """
        color_map = []
        for thresh_var, color_var, _, _, _ in self.color_map_entries:
            try:
                threshold_str = thresh_var.get().strip()
                if threshold_str.lower() == 'inf':
                    threshold = float('inf')
                elif threshold_str.lower() == '-inf':
                    threshold = float('-inf')
                else:
                    threshold = float(threshold_str)

                hex_color = color_var.get().strip()
                if not re.match(r'^#[0-9a-fA-F]{6}$', hex_color):
                    messagebox.showwarning("Color Map Parse Error", f"Invalid stored hex color: {hex_color}. Using default black.")
                    hex_color = "#000000"
                color_map.append((threshold, hex_color))
            except ValueError as e:
                messagebox.showwarning("Color Map Parse Error", f"Skipping invalid color map entry: '{thresh_var.get()}' - {e}")
        color_map.sort(key=lambda x: x[0])
        return color_map

    def _get_color_for_percentage(self, percentage, color_map):
        """
        Determines the appropriate color for a given percentage based on the color map.
        """
        if not color_map:
            return "#000000" # Default black if no color map

        for threshold, color in color_map:
            if percentage <= threshold:
                return color
        return color_map[-1][1]

    def calculate_and_prepare_percentage_content(self):
        """
        Calculates the percentage increase for numerical words in File 2 compared to File 1,
        and prepares the formatted content and coloring data.
        This method does NOT update the text_area2 directly.
        Numbers enclosed in square brackets `[]` will be excluded from percentage calculation.
        """
        content1 = self.text_area1.get(1.0, tk.END).strip()
        content2 = self.original_content2.strip() # Use original content of file 2

        if not content1 or not content2:
            self.percentage_formatted_content2 = self.original_content2 # Fallback
            self.percentage_data_for_coloring = []
            return

        lines1 = content1.split('\n')
        lines2 = content2.split('\n')

        exclude_lines_pattern = self.exclude_lines_regex_var.get()
        exclude_words_pattern = self.exclude_words_regex_var.get()

        compiled_line_regex = None
        if exclude_lines_pattern:
            try:
                compiled_line_regex = re.compile(exclude_lines_pattern)
            except re.error as e:
                messagebox.showerror("Regex Error", f"Invalid Exclude Lines Regex: {e}")
                return

        compiled_word_regex = None
        if exclude_words_pattern:
            try:
                compiled_word_regex = re.compile(exclude_words_pattern)
            except re.error as e:
                messagebox.showerror("Regex Error", f"Invalid Exclude Words Regex: {e}")
                return

        min_lines = min(len(lines1), len(lines2))
        
        formatted_lines = []
        self.percentage_data_for_coloring = [] # Reset for new calculation

        current_char_offset = 0 # Track character offset for tag indices

        for i in range(min_lines):
            line1 = lines1[i]
            line2 = lines2[i]
            
            if compiled_line_regex and compiled_line_regex.search(line1):
                formatted_lines.append(line2)
                current_char_offset += len(line2) + 1 # +1 for newline
                continue

            # Find all standalone numbers in both lines
            # \b\d+\b ensures that only pure numbers (not part of other words) are matched
            numbers1_iter = re.finditer(r'\b\d+\b', line1)
            numbers2_iter = re.finditer(r'\b\d+\b', line2)

            numbers1_matches = [(m, int(m.group(0))) for m in numbers1_iter]
            numbers2_matches = [(m, int(m.group(0))) for m in numbers2_iter]

            if len(numbers1_matches) != len(numbers2_matches) or not numbers1_matches:
                formatted_lines.append(line2)
                current_char_offset += len(line2) + 1
                continue

            line_parts = []
            last_end = 0
            for j in range(len(numbers1_matches)):
                m1, val1 = numbers1_matches[j]
                m2, val2 = numbers2_matches[j]
                
                line_parts.append(line2[last_end:m2.start()])

                # Check if the number in line1 is within square brackets, allowing for optional spaces
                is_in_brackets = False
                # Look for '[' followed by optional spaces before the number
                pre_match_start = max(0, m1.start() - 2) # Check a few chars before
                pre_match_text = line1[pre_match_start:m1.start()]
                if re.search(r'\[\s*$', pre_match_text):
                    # Look for ']' preceded by optional spaces after the number
                    post_match_end = min(len(line1), m1.end() + 2) # Check a few chars after
                    post_match_text = line1[m1.end():post_match_end]
                    if re.match(r'^\s*\]', post_match_text):
                        is_in_brackets = True

                # If it's in brackets OR matches the exclude words regex, append as is
                if is_in_brackets or (compiled_word_regex and compiled_word_regex.search(m1.group(0))):
                    line_parts.append(m2.group(0))
                else:
                    # Apply percentage formatting as before
                    percentage_str_val = ""
                    increase_percent = 0.0

                    if val1 != 0:
                        increase_percent = ((val2 - val1) / val1) * 100
                        percentage_str_val = f"{increase_percent:.0f}%"
                    elif val1 == 0 and val2 == 0:
                        percentage_str_val = "0%"
                    else:
                        percentage_str_val = "Inf%"

                    line_parts.append(str(val2))
                    line_parts.append("(")
                    
                    # Store indices relative to the start of the entire text_area2 content
                    percentage_start_offset = current_char_offset + len("".join(line_parts))
                    line_parts.append(percentage_str_val)
                    percentage_end_offset = current_char_offset + len("".join(line_parts))

                    self.percentage_data_for_coloring.append({
                        'start_offset': percentage_start_offset,
                        'end_offset': percentage_end_offset,
                        'percentage': increase_percent
                    })
                    line_parts.append(")")
                
                last_end = m2.end()

            line_parts.append(line2[last_end:])
            formatted_line = "".join(line_parts)
            formatted_lines.append(formatted_line)
            current_char_offset += len(formatted_line) + 1 # +1 for newline

        for i in range(min_lines, len(lines2)):
            formatted_lines.append(lines2[i])
            current_char_offset += len(lines2[i]) + 1

        self.percentage_formatted_content2 = "\n".join(formatted_lines)

    def toggle_percentage_display(self):
        """
        Toggles the display of percentage changes in File 2's text area.
        """
        self.show_percentage_changes.set(not self.show_percentage_changes.get())
        self._update_display_content_and_colors()

    def toggle_apply_colors(self):
        """
        Toggles whether colors are applied to percentage changes.
        """
        self.apply_colors_active.set(not self.apply_colors_active.get())
        self._update_display_content_and_colors()

    def _update_display_content_and_colors(self):
        """
        Updates the content and applies colors to text_area2 based on current toggle states.
        """
        # Clear all content and existing tags from text_area2
        self.text_area2.delete(1.0, tk.END)
        for tag_name in self.text_area2.tag_names():
            if tag_name.startswith("color_"):
                self.text_area2.tag_remove(tag_name, "1.0", tk.END)
                self.text_area2.tag_delete(tag_name)

        if self.show_percentage_changes.get():
            self.text_area2.insert(tk.END, self.percentage_formatted_content2)
            if self.apply_colors_active.get():
                self._apply_colors_to_percentages()
        else:
            self.text_area2.insert(tk.END, self.original_content2)
        
        self.text_area2.see(tk.END) # Scroll to the end

    def _apply_colors_to_percentages(self):
        """
        Applies colors to the percentage changes in text_area2 based on the current color map.
        This function is called by _update_display_content_and_colors.
        """
        if not self.percentage_data_for_coloring:
            return # No percentage data to color

        color_map = self._parse_color_map()

        for data in self.percentage_data_for_coloring:
            start_offset = data['start_offset']
            end_offset = data['end_offset']
            percentage = data['percentage']

            calculated_color = self._get_color_for_percentage(percentage, color_map)
            
            # Convert character offsets to Tkinter text indices
            start_index_in_text = f"1.0 + {start_offset} chars"
            end_index_in_text = f"1.0 + {end_offset} chars"

            color_tag_name = f"color_{calculated_color.replace('#', '')}"
            self.text_area2.tag_configure(color_tag_name, foreground=calculated_color)
            self.text_area2.tag_add(color_tag_name, start_index_in_text, end_index_in_text)

    def execute_command(self, event=None):
        """
        Executes the command entered in the command entry for both loaded files
        and displays the output in their respective text areas.
        Replaces %P with full path, %F with basename, %U with custom_u, and %K with custom_k.
        Args:
            event (tk.Event, optional): The event object if triggered by a key press. Defaults to None.
        """
        command_template = self.command_var.get()

        if not self.file_path1 and not self.file_path2:
            messagebox.showwarning("Warning", "Please load at least one file before executing a command.")
            return

        # Process File 1
        if self.file_path1:
            full_path1 = self.file_path1
            base_name1 = os.path.basename(full_path1)
            custom_u1 = self.u_var1.get()
            custom_k1 = self.k_var1.get()

            executed_command1 = command_template.replace('%P', full_path1).replace('%F', base_name1)
            executed_command1 = executed_command1.replace('%U', custom_u1).replace('%K', custom_k1)

            self.text_area1.delete(1.0, tk.END) # Clear existing content
            self.text_area1.insert(tk.END, f"--- Executing for {base_name1} ---\n")
            self.text_area1.insert(tk.END, f"Command: {executed_command1}\n\n")
            self._run_command_and_display_output(executed_command1, self.text_area1)
            self.text_area1.see(tk.END) # Scroll to the end

        # Process File 2
        if self.file_path2:
            full_path2 = self.file_path2
            base_name2 = os.path.basename(full_path2)
            custom_u2 = self.u_var2.get()
            custom_k2 = self.k_var2.get()

            executed_command2 = command_template.replace('%P', full_path2).replace('%F', base_name2)
            executed_command2 = executed_command2.replace('%U', custom_u2).replace('%K', custom_k2)

            # For File 2, we execute command, then store its output as original content
            # and recalculate percentages based on this new 'original' content.
            # Then update display.
            temp_output_widget = scrolledtext.ScrolledText(self.master) # Temporary widget to capture output
            self._run_command_and_display_output(executed_command2, temp_output_widget)
            self.original_content2 = temp_output_widget.get(1.0, tk.END).strip()
            temp_output_widget.destroy() # Clean up temporary widget

            self.calculate_and_prepare_percentage_content()
            self._update_display_content_and_colors()


    def _run_command_and_display_output(self, command, text_widget):
        """
        Helper function to run a command and display its output in a given text widget.
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                executable='/bin/bash'
            )

            if result.stdout:
                text_widget.insert(tk.END, "STDOUT:\n")
                text_widget.insert(tk.END, result.stdout)
            if result.stderr:
                text_widget.insert(tk.END, "STDERR:\n")
                text_widget.insert(tk.END, result.stderr)

            text_widget.insert(tk.END, f"Exit Code: {result.returncode}\n\n")

        except FileNotFoundError:
            text_widget.insert(tk.END, "Error: Bash executable not found. Make sure bash is installed and in your PATH.\n\n")
        except Exception as e:
            text_widget.insert(tk.END, f"An error occurred during command execution: {e}\n\n")

    def save_as_html(self):
        """
        Saves the content of both text areas into a single HTML file,
        applying colors to percentages in File 2 if currently active.
        """
        if not self.file_path1 and not self.file_path2:
            messagebox.showwarning("Warning", "No files loaded to save as HTML.")
            return

        html_file_path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            title="Save as HTML"
        )

        if html_file_path:
            content1 = self.text_area1.get(1.0, tk.END).strip()
            
            # Generate content2 for HTML based on current display logic and color settings
            content2_for_html = ""
            if self.show_percentage_changes.get():
                # If percentage changes are supposed to be shown
                raw_text_for_html = self.percentage_formatted_content2
                percentage_data = self.percentage_data_for_coloring
                
                html_content2_parts = []
                last_offset = 0
                color_map = self._parse_color_map() if self.apply_colors_active.get() else None

                for data in percentage_data:
                    start_offset = data['start_offset']
                    end_offset = data['end_offset']
                    percentage_value = data['percentage']

                    # Add plain text before the colored segment
                    html_content2_parts.append(raw_text_for_html[last_offset:start_offset])
                    
                    segment_text = raw_text_for_html[start_offset:end_offset]

                    if self.apply_colors_active.get() and color_map:
                        calculated_color = self._get_color_for_percentage(percentage_value, color_map)
                        html_content2_parts.append(f'<span style="color: {calculated_color};">{segment_text}</span>')
                    else:
                        html_content2_parts.append(segment_text)
                    
                    last_offset = end_offset
                
                # Add any remaining plain text after the last colored segment
                html_content2_parts.append(raw_text_for_html[last_offset:])
                content2_for_html = "".join(html_content2_parts)
            else:
                # If original content is supposed to be shown
                content2_for_html = self.original_content2.strip()

            name1 = os.path.basename(self.file_path1) if self.file_path1 else "File 1 (No file selected)"
            name2 = os.path.basename(self.file_path2) if self.file_path2 else "File 2 (No file selected)"

            html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TwinActionViewer - HTML Export</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f4f7f6;
            color: #333;
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
        }}
        .file-container {{
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
            padding: 20px;
            flex: 1;
            min-width: 450px; /* Minimum width for each container */
            max-width: 600px; /* Maximum width for each container */
            display: flex;
            flex-direction: column;
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            width: 100%;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 0;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }}
        pre {{
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            white-space: pre-wrap; /* Wrap long lines */
            word-wrap: break-word; /* Break words if necessary */
            flex-grow: 1; /* Allow pre to take available space */
        }}
        @media (max-width: 960px) {{
            .file-container {{
                min-width: unset;
                max-width: 100%;
                flex: none;
            }}
        }}
    </style>
</head>
<body>
    <h1>File Content Export</h1>
    <div class="file-container">
        <h2>Content of {name1}</h2>
        <pre>{content1}</pre>
    </div>
    <div class="file-container">
        <h2>Content of {name2}</h2>
        <pre>{content2_for_html}</pre>
    </div>
</body>
</html>
            """
            try:
                with open(html_file_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                messagebox.showinfo("Success", f"Content saved to {html_file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save HTML file: {e}")

    def save_as_jpeg(self):
        """
        Captures the entire application window and saves it as a JPEG,
        and attempts to copy it to the clipboard as PNG.
        """
        try:
            # Get the bounding box of the entire master window relative to the screen
            x = self.master.winfo_rootx()
            y = self.master.winfo_rooty()
            width = self.master.winfo_width()
            height = self.master.winfo_height()
            bbox = (x, y, x + width, y + height)

            # Capture the screenshot
            screenshot = ImageGrab.grab(bbox)

            # Convert to RGB for JPEG saving (JPEG does not support alpha channel)
            jpeg_screenshot = screenshot.convert('RGB')

            # Prompt user for save location for JPEG
            file_path = filedialog.asksaveasfilename(
                defaultextension=".jpg",
                filetypes=[("JPEG files", "*.jpg"), ("All files", "*.*")],
                title="Save Screenshot as JPEG"
            )
            if file_path:
                jpeg_screenshot.save(file_path, "JPEG")
                messagebox.showinfo("Success", f"Screenshot saved to {file_path}")
            
            # Attempt to copy to clipboard as PNG (PNG supports alpha and is generally preferred for clipboard)
            try:
                # Create a temporary BytesIO object to save the PNG to memory
                from io import BytesIO
                png_buffer = BytesIO()
                # Ensure the image for clipboard is also converted to a compatible mode if it was RGBA
                # PNG supports RGBA, so we can save the original 'screenshot' directly if it's RGBA
                # If it's a simple RGB image, saving as PNG is fine too.
                screenshot.save(png_buffer, format="PNG")
                
                # Get the raw PNG data
                png_data = png_buffer.getvalue()

                # Attempt to put PNG data directly to clipboard
                # This part is highly OS-dependent and might require external tools or specific Tkinter/Pillow integrations
                # For basic Pillow clipboard support, 'clipboard:' pseudo-file is used.
                screenshot.save("clipboard:clipboard", format="PNG")
                messagebox.showinfo("Clipboard", "Screenshot copied to clipboard as PNG. (Note: Clipboard functionality may vary by OS.)")
            except Exception as clipboard_e:
                messagebox.showwarning("Clipboard Warning", f"Failed to copy screenshot to clipboard: {clipboard_e}. This feature may not be fully supported on your operating system.")

        except ImportError:
            messagebox.showerror("Error", "Pillow library not found. Please install it: pip install Pillow")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture or save screenshot: {e}")

def main():
    root = tk.Tk()
    app = FileViewerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
