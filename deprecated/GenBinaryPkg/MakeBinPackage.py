import os

# Set the path to the spec file inside the cloned repository
spec_src = 'cloned_repo/packaging/spec'  # Change this path as needed
output_dir = 'output_dir'
os.makedirs(output_dir, exist_ok=True)

# Parse the spec file to extract package metadata
fields = {}
with open(spec_src, 'r') as f:
    for line in f:
        if ':' in line:
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()

# Extract required fields with defaults if not present
name = fields.get('Name', 'unknown')
version = fields.get('Version', '0.1.0')
release = fields.get('Release', '1%{?dist}')
summary = fields.get('Summary', '')
license_ = fields.get('License', '')
url = fields.get('URL', '')

# Collect file list from output_dir, preserving directory structure
file_list = []
for root, dirs, files in os.walk(output_dir):
    for file in files:
        # Store the path relative to output_dir for the %files section
        abs_path = os.path.join(root, file)
        rel_path = abs_path.replace(output_dir, '', 1)
        if not rel_path:
            rel_path = '/'
        file_list.append(rel_path)

# Create the .spec file in the output directory
spec_path = os.path.join(output_dir, f'{name}.spec')
with open(spec_path, 'w') as f:
    f.write(f'''Name: {name}
Version: {version}
Release: {release}
Summary: {summary}
License: {license_}
URL: {url}
Source0: %{name}-%{version}.tar.gz

%description
{summary}

%prep

%build

%install

%files
''')
    for path in file_list:
        f.write(f"{path}\n")
    f.write('\n%changelog\n')
