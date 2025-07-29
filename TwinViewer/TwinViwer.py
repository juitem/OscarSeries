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

        self.button_percentage = tk.Button(self.options_row_frame, text="%", command=self.calculate_and_display_percentage,
                                            bg="#42A5F5", fg="white", font=("Arial", 10, "bold"), bd=2, relief=tk.RAISED) # Softer blue
        self.button_percentage.pack(side=tk.LEFT, padx=5)

        # New: Apply Colors button
        self.button_apply_colors = tk.Button(self.options_row_frame, text="Apply Colors", command=self.apply_percentage_colors,
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

        # List to store calculated percentage data for coloring
        self.calculated_percentage_data = []


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
            # We no longer add a separate add_color_map_entry button, but use the existing data
            # to populate the fixed number of color rules.
            # The add_color_map_entry method is now simplified to just create the rule_frame.
            self.add_color_map_entry(initial_threshold=str(thresh), initial_color=color)
        self._update_color_map_range_labels() # Initial update of labels

    def add_color_map_entry(self, initial_threshold="", initial_color=""):
        """
        Adds a new set of widgets for a color map entry (range label, threshold, color picker, hex input, remove button)
        and packs them horizontally into the container.
        """
        # Create a sub-frame for each color rule to group its elements horizontally
        # This frame will then be packed horizontally into the main color_map_entries_container
        rule_frame = tk.Frame(self.color_map_entries_container, bg="#E3F2FD", bd=1, relief=tk.SUNKEN)
        rule_frame.pack(side=tk.LEFT, padx=2, pady=1) # Pack horizontally with small padding

        range_label = tk.Label(rule_frame, text="", bg="#E3F2FD", font=("Arial", 8))
        range_label.pack(side=tk.LEFT, padx=(0, 2)) # Combined range label

        thresh_var = tk.StringVar(value=initial_threshold)
        color_hex_var = tk.StringVar(value=initial_color)

        # Adjusted width to 3 and font size to 8
        entry_thresh = tk.Entry(rule_frame, textvariable=thresh_var, width=3, bd=1, relief=tk.SUNKEN, font=("Arial", 8))
        entry_thresh.pack(side=tk.LEFT, padx=(0, 2))
        # Bind KeyRelease to update labels AND apply colors
        entry_thresh.bind("<KeyRelease>", lambda event: (self._update_color_map_range_labels(), self.apply_percentage_colors()))

        color_display_button = tk.Button(rule_frame, text="", width=1, height=1, # Reduced width and height
                                         command=lambda: self.pick_color(color_hex_var, color_display_button), # Removed hex_entry
                                         bg=initial_color if initial_color else "#FFFFFF", bd=1, relief=tk.RAISED)
        color_display_button.pack(side=tk.LEFT, padx=(0, 2))

        # Removed entry_color_hex and its packing and binding
        # Removed remove_button and its packing

        self.color_map_entries.append((thresh_var, color_hex_var, rule_frame, color_display_button, range_label)) # Store rule_frame and labels
        self._update_color_map_range_labels() # Update labels after adding new entry

    def remove_color_map_entry(self, rule_frame, thresh_var, color_hex_var, color_display_button, range_label):
        """
        Removes a color map entry rule_frame from the UI and internal list.
        This method is now a placeholder as the "X" button is removed.
        """
        messagebox.showinfo("Info", "Color rules can only be modified in the default settings.")
        # rule_frame.destroy()
        # self.color_map_entries = [
        #     entry for entry in self.color_map_entries
        #     if not (entry[0] == thresh_var and entry[1] == color_hex_var and entry[3] == color_display_button and entry[4] == range_label)
        # ]
        # self._update_color_map_range_labels() # Update labels after removing an entry


    def _update_color_map_range_labels(self):
        """
        Updates the min/max range labels for all color map entries based on their sorted thresholds.
        """
        # Create a temporary list of (threshold, index_in_color_map_entries) for sorting
        sortable_entries = []
        for i, (thresh_var, _, _, _, _) in enumerate(self.color_map_entries): # Access range_label
            try:
                threshold_str = thresh_var.get().strip()
                if threshold_str.lower() == 'inf':
                    threshold = float('inf')
                elif threshold_str.lower() == '-inf': # Handle -inf for sorting
                    threshold = float('-inf')
                else:
                    threshold = float(threshold_str)
                sortable_entries.append((threshold, i))
            except ValueError:
                # If threshold is invalid, treat it as inf for sorting to put it at the end
                sortable_entries.append((float('inf'), i)) # Invalid thresholds go to the end

        sortable_entries.sort(key=lambda x: x[0])

        # Now, iterate through the sorted entries and update the labels
        for i, (current_threshold_val, original_index) in enumerate(sortable_entries):
            _, _, _, _, range_label = self.color_map_entries[original_index] # Access range_label

            min_bound_str = ""
            if i == 0:
                min_bound_str = "-inf"
            else:
                prev_threshold_val = sortable_entries[i-1][0]
                min_bound_str = f"{prev_threshold_val:.0f}" if prev_threshold_val != float('-inf') else "-inf"
            
            max_bound_str = f"{current_threshold_val:.0f}" if current_threshold_val != float('inf') else "inf"

            range_label.config(text=f"{min_bound_str}~{max_bound_str}") # Removed "Range:" prefix


    def pick_color(self, color_hex_var, color_button): # Removed hex_entry from arguments
        """
        Opens a color picker dialog and updates the color hex variable and button background.
        """
        color_code = tkinter.colorchooser.askcolor(title="Choose color")[1] # [1] is the hex code
        if color_code:
            color_hex_var.set(color_code)
            color_button.config(bg=color_code)
            # After picking a color, re-apply colors to update the display
            self.apply_percentage_colors()

    def update_color_button_from_entry(self, color_hex_var, color_button):
        """
        Updates the color button's background based on the hex code entered in the entry field.
        This method is now a placeholder as the hex input entry is removed.
        """
        # hex_code = color_hex_var.get()
        # if re.match(r'^#[0-9a-fA-F]{6}$', hex_code):
        #     color_button.config(bg=hex_code)
        # else:
        #     color_button.config(bg="#FFFFFF") # Revert to white if invalid hex
        pass # No longer needed as hex input entry is removed

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
                self.display_file_content(self.file_path2, self.text_area2)

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
        elif file_number == 2:
            file_path = self.file_path_var2.get()
            self.file_path2 = file_path # Update instance variable
            text_widget = self.text_area2
        else:
            return

        if file_path:
            self.display_file_content(file_path, text_widget)

    def display_file_content(self, file_path, text_widget):
        """
        Reads content from a given file path and updates the specified text widget.
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
            # Clear the entry field if file not found
            if text_widget == self.text_area1:
                self.file_path_var1.set("")
            elif text_widget == self.text_area2:
                self.file_path_var2.set("")
        except Exception as e:
            messagebox.showerror("Error", f"Error reading file {file_path}: {e}")
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, f"Error reading file: {e}")
            # Clear the entry field if error reading
            if text_widget == self.text_area1:
                self.file_path_var1.set("")
            elif text_widget == self.text_area2:
                self.file_path_var2.set("")

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
        self.display_file_content(self.file_path1, self.text_area1)
        self.display_file_content(self.file_path2, self.text_area2)

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
                self.display_file_content(self.file_path2, self.text_area2)
            else:
                messagebox.showinfo("Info", "File 2 path is not set. Please browse or enter a file path.")

    def _parse_color_map(self):
        """
        Parses the color map entries from the UI into a sorted list of (threshold, hex_color) tuples.
        """
        color_map = []
        for thresh_var, color_var, _, _, _ in self.color_map_entries: # Unpack all elements
            try:
                threshold_str = thresh_var.get().strip()
                if threshold_str.lower() == 'inf': # Handle 'inf' for infinite
                    threshold = float('inf')
                elif threshold_str.lower() == '-inf':
                    threshold = float('-inf')
                else:
                    threshold = float(threshold_str)

                hex_color = color_var.get().strip()
                # Since hex_color entry is removed, we just use the stored value
                if not re.match(r'^#[0-9a-fA-F]{6}$', hex_color):
                    # Fallback to a default color if the stored hex is invalid
                    messagebox.showwarning("Color Map Parse Error", f"Invalid stored hex color: {hex_color}. Using default black.")
                    hex_color = "#000000"
                color_map.append((threshold, hex_color))
            except ValueError as e:
                messagebox.showwarning("Color Map Parse Error", f"Skipping invalid color map entry: '{thresh_var.get()}' - {e}")
        color_map.sort(key=lambda x: x[0]) # Sort by threshold
        return color_map

    def _get_color_for_percentage(self, percentage, color_map):
        """
        Determines the appropriate color for a given percentage based on the color map.
        """
        # Ensure color_map is not empty
        if not color_map:
            return "#000000" # Default black if no color map

        # Find the appropriate color based on the percentage
        for threshold, color in color_map:
            if percentage <= threshold:
                return color
        # If percentage is greater than all thresholds, use the last color
        return color_map[-1][1]

    def calculate_and_display_percentage(self):
        """
        Calculates the percentage increase for numerical words in File 2 compared to File 1,
        and displays the modified content in File 2's text area.
        This method will NOT apply colors; it only calculates and inserts text.
        """
        content1 = self.text_area1.get(1.0, tk.END).strip()
        content2 = self.text_area2.get(1.0, tk.END).strip()

        if not content1 or not content2:
            messagebox.showwarning("Warning", "Please load content into both file areas to calculate percentages.")
            return

        lines1 = content1.split('\n')
        lines2 = content2.split('\n')

        # Get regex patterns from entry fields
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
        
        # Clear all content and existing tags from text_area2 before inserting new content
        self.text_area2.delete(1.0, tk.END)
        # Clear previously stored percentage data
        self.calculated_percentage_data = []

        for i in range(min_lines):
            line1 = lines1[i]
            line2 = lines2[i]

            # Check if the current line should be excluded
            if compiled_line_regex and compiled_line_regex.search(line1):
                self.text_area2.insert(tk.END, line2 + "\n")
                continue

            numbers1_iter = re.finditer(r'\b\d+\b', line1)
            numbers2_iter = re.finditer(r'\b\d+\b', line2)

            numbers1_matches = [(m, int(m.group(0))) for m in numbers1_iter]
            numbers2_matches = [(m, int(m.group(0))) for m in numbers2_iter]

            if len(numbers1_matches) != len(numbers2_matches) or not numbers1_matches:
                self.text_area2.insert(tk.END, line2 + "\n")
                continue

            last_end = 0
            for j in range(len(numbers1_matches)):
                m1, val1 = numbers1_matches[j]
                m2, val2 = numbers2_matches[j]
                
                # Insert text before the current number from original line2
                self.text_area2.insert(tk.END, line2[last_end:m2.start()])

                # Check if the current word (number) should be excluded
                if compiled_word_regex and compiled_word_regex.search(m1.group(0)):
                    self.text_area2.insert(tk.END, m2.group(0)) # Insert original number from line2
                else:
                    percentage_str_val = ""
                    increase_percent = 0.0

                    if val1 != 0:
                        increase_percent = ((val2 - val1) / val1) * 100
                        percentage_str_val = f"{increase_percent:.0f}%"
                    elif val1 == 0 and val2 == 0:
                        percentage_str_val = "0%"
                    else: # val1 is 0, val2 is not 0 (infinite increase)
                        percentage_str_val = "Inf%"

                    # Insert the original number part (val2) without color
                    self.text_area2.insert(tk.END, str(val2))
                    
                    # Capture the start index for the entire "(XX%)" string
                    full_percentage_start_index = self.text_area2.index(tk.END) 
                    
                    self.text_area2.insert(tk.END, "(") # Insert opening parenthesis
                    self.text_area2.insert(tk.END, percentage_str_val) # Insert percentage value
                    self.text_area2.insert(tk.END, ")") # Insert closing parenthesis
                    
                    # Capture the end index for the entire "(XX%)" string
                    full_percentage_end_index = self.text_area2.index(tk.END) 
                    
                    self.calculated_percentage_data.append({
                        'start': full_percentage_start_index, # Use the new start index
                        'end': full_percentage_end_index,     # Use the new end index
                        'percentage': increase_percent
                    })
                
                last_end = m2.end()

            # Insert any remaining text after the last number in line2
            self.text_area2.insert(tk.END, line2[last_end:] + "\n")

        # Append any remaining lines from content2 if it was longer than content1
        for i in range(min_lines, len(lines2)):
            self.text_area2.insert(tk.END, lines2[i] + "\n")

        self.text_area2.see(tk.END) # Scroll to the end

    def apply_percentage_colors(self):
        """
        Applies colors to the percentage changes in text_area2 based on the current color map.
        """
        if not self.calculated_percentage_data:
            messagebox.showwarning("Warning", "No percentage data to color. Please run '%' first.")
            return

        # Remove all existing color tags before re-applying
        for tag_name in self.text_area2.tag_names():
            if tag_name.startswith("color_"):
                self.text_area2.tag_remove(tag_name, "1.0", tk.END)
                self.text_area2.tag_delete(tag_name) # Delete the tag configuration too

        color_map = self._parse_color_map()

        for data in self.calculated_percentage_data:
            start_index = data['start']
            end_index = data['end']
            percentage = data['percentage']

            calculated_color = self._get_color_for_percentage(percentage, color_map)
            
            color_tag_name = f"color_{calculated_color.replace('#', '')}"
            if color_tag_name not in self.text_area2.tag_names():
                self.text_area2.tag_configure(color_tag_name, foreground=calculated_color)
            
            self.text_area2.tag_add(color_tag_name, start_index, end_index)

        # messagebox.showinfo("Colors Applied", "Percentage colors have been applied.") # Removed for smoother UX


    def execute_command(self, event=None): # Added event=None to handle both button click and Enter key
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

            self.text_area2.delete(1.0, tk.END) # Clear existing content
            self.text_area2.insert(tk.END, f"--- Executing for {base_name2} ---\n")
            self.text_area2.insert(tk.END, f"Command: {executed_command2}\n\n")
            self._run_command_and_display_output(executed_command2, self.text_area2)
            self.text_area2.see(tk.END) # Scroll to the end

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
                text_widget.insert(tk.END, "STDERR:\n")
                text_widget.insert(tk.END, result.stderr)

            text_widget.insert(tk.END, f"Exit Code: {result.returncode}\n\n")

        except FileNotFoundError:
            text_widget.insert(tk.END, "Error: Bash executable not found. Make sure bash is installed and in your PATH.\n\n")
        except Exception as e:
            text_widget.insert(tk.END, f"An error occurred during command execution: {e}\n\n")

    def save_as_html(self):
        """
        Saves the content of both text areas into a single HTML file.
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
            content2 = self.text_area2.get(1.0, tk.END).strip()

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
        <pre>{content2}</pre>
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
        Captures the application window from the paned_window downwards and saves it as a JPEG.
        """
        try:
            # Get the bounding box of the paned_window relative to the screen
            x = self.paned_window.winfo_rootx()
            y = self.paned_window.winfo_rooty()
            width = self.paned_window.winfo_width()
            height = self.paned_window.winfo_height()
            bbox = (x, y, x + width, y + height)

            # Capture the screenshot
            screenshot = ImageGrab.grab(bbox)

            # Prompt user for save location
            file_path = filedialog.asksaveasfilename(
                defaultextension=".jpg",
                filetypes=[("JPEG files", "*.jpg"), ("All files", "*.*")],
                title="Save Screenshot as JPEG"
            )
            if file_path:
                screenshot.save(file_path, "JPEG")
                messagebox.showinfo("Success", f"Screenshot saved to {file_path}")
            
            # Note: Image clipboard functionality is highly platform-dependent
            # and not reliably cross-platform with basic Tkinter/Pillow.
            # For robust cross-platform clipboard, external libraries or OS-specific
            # commands would be needed (e.g., xclip on Linux).
            # This implementation focuses on file saving.

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
