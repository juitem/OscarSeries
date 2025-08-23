import os
import struct

def get_pe_sections(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
    pe_header_offset = e_lfanew
    if data[pe_header_offset:pe_header_offset+4] != b'PE\0\0':
        return None
    file_header_offset = pe_header_offset + 4
    number_of_sections = struct.unpack_from('<H', data, file_header_offset + 2)[0]
    size_of_optional_header = struct.unpack_from('<H', data, file_header_offset + 16)[0]
    section_header_offset = file_header_offset + 20 + size_of_optional_header

    sections = {}
    for i in range(number_of_sections):
        offset = section_header_offset + 40 * i
        name_bytes = data[offset:offset + 8]
        name = name_bytes.split(b'\x00')[0].decode(errors='ignore')
        virtual_size = struct.unpack_from('<I', data, offset + 8)[0]
        if name not in sections:
            sections[name] = 0
        sections[name] += virtual_size
    return sections

def get_sections_total_size(directory_path):
    total_sizes = {}
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.dll') or file.lower().endswith('.exe'):
                file_path = os.path.join(root, file)
                sections = get_pe_sections(file_path)
                if not sections:
                    continue
                for key, value in sections.items():
                    if key not in total_sizes:
                        total_sizes[key] = 0
                    total_sizes[key] += value
    return total_sizes

# 실제 사용시 각 디렉토리 경로 입력 필요
sizes_dir1 = get_sections_total_size('디렉토리1 경로')
sizes_dir2 = get_sections_total_size('디렉토리2 경로')

print("첫번째 디렉토리 섹션 총합:", sizes_dir1)
print("두번째 디렉토리 섹션 총합:", sizes_dir2)
