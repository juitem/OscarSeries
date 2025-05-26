import sys
import csv
import re

def parse_args(args):
    # 첫 번째는 BuildFunc 값, 나머지는 FieldName="Value"
    build_func = args[0]
    updates = {}
    for arg in args[1:]:
        m = re.match(r'([^=]+)="(.*)"', arg)
        if m:
            updates[m.group(1)] = m.group(2)
        else:
            print(f"Invalid argument: {arg}", file=sys.stderr)
            sys.exit(1)
    return build_func, updates

def get_row(csv_file, build_func):
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['BuildFunc'] == build_func:
                print(','.join(row.keys()))
                print(','.join([row[k] for k in row.keys()]))
                return
    print(f"No row found with BuildFunc={build_func}", file=sys.stderr)
    sys.exit(1)

def update_fields(csv_file, build_func, updates):
    rows = []
    updated = False
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row['BuildFunc'] == build_func:
                for k, v in updates.items():
                    if k in row:
                        row[k] = v
                updated = True
            rows.append(row)
    if updated:
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        print(f"No row found with BuildFunc={build_func}", file=sys.stderr)
        sys.exit(1)

def get_field(csv_file, build_func, field_name):
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['BuildFunc'] == build_func:
                if field_name in row:
                    print(row[field_name])
                    return
                else:
                    print(f"Field '{field_name}' not found", file=sys.stderr)
                    sys.exit(1)
    print(f"No row found with BuildFunc={build_func}", file=sys.stderr)
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: csv_helper.py <command> ...', file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'get':
        if len(sys.argv) != 4:
            print('Usage: csv_helper.py get <csv_file> <BuildFunc>', file=sys.stderr)
            sys.exit(1)
        get_row(sys.argv[2], sys.argv[3])
    elif cmd == 'update':
        if len(sys.argv) < 5:
            print('Usage: csv_helper.py update <csv_file> <BuildFunc> Field1="Value1" [Field2="Value2" ...]', file=sys.stderr)
            sys.exit(1)
        csv_file = sys.argv[2]
        build_func, updates = parse_args(sys.argv[3:])
        update_fields(csv_file, build_func, updates)
    elif cmd == 'getfield':
        if len(sys.argv) != 5:
            print('Usage: csv_helper.py getfield <csv_file> <BuildFunc> <FieldName>', file=sys.stderr)
            sys.exit(1)
        csv_file = sys.argv[2]
        build_func = sys.argv[3]
        field_name = sys.argv[4]
        get_field(csv_file, build_func, field_name)


