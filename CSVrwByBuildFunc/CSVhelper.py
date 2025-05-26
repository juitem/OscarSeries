import sys
import csv
import re

def parse_args(args):
    """
    Parse arguments for update command.
    The first argument is BuildFunc, others are FieldName="Value".
    """
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
    """
    Print the header and the row where BuildFunc matches.
    """
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
    """
    Update fields for the row where BuildFunc matches.
    If a field does not exist, add it as a new column.
    """
    rows = []
    updated = False
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        # Get existing fieldnames, or empty list if file is empty
        fieldnames = reader.fieldnames if reader.fieldnames else []
        # Add new fields to fieldnames if not present
        for k in updates:
            if k not in fieldnames:
                fieldnames.append(k)
        for row in reader:
            # Ensure all fields exist in each row (fill with empty string if missing)
            for k in fieldnames:
                if k not in row:
                    row[k] = ''
            if row['BuildFunc'] == build_func:
                for k, v in updates.items():
                    row[k] = v
                updated = True
            rows.append(row)
    if updated:
        # Write back with possibly updated fieldnames and rows
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        print(f"No row found with BuildFunc={build_func}", file=sys.stderr)
        sys.exit(1)

def get_field(csv_file, build_func, field_name):
    """
    Print the value of a specific field in the row where BuildFunc matches.
    """
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


def delete_row(csv_file, build_func):
    """
    Delete the row where BuildFunc matches the given value.
    """
    rows = []
    deleted = False
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row['BuildFunc'] == build_func:
                deleted = True
                continue  # Skip this row (delete)
            rows.append(row)
    if deleted:
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        print(f"No row found with BuildFunc={build_func}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    # Main command dispatcher
    if len(sys.argv) < 2:
        print('Usage: csv_helper.py <command> ...', file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'get':
        # Get the full row (with header) by BuildFunc
        if len(sys.argv) != 4:
            print('Usage: csv_helper.py get <csv_file> <BuildFunc>', file=sys.stderr)
            sys.exit(1)
        get_row(sys.argv[2], sys.argv[3])
    elif cmd == 'update':
        # Update fields (add columns if necessary)
        if len(sys.argv) < 5:
            print('Usage: csv_helper.py update <csv_file> <BuildFunc> Field1="Value1" [Field2="Value2" ...]', file=sys.stderr)
            sys.exit(1)
        csv_file = sys.argv[2]
        build_func, updates = parse_args(sys.argv[3:])
        update_fields(csv_file, build_func, updates)
    elif cmd == 'getfield':
        # Get a specific field value by BuildFunc
        if len(sys.argv) != 5:
            print('Usage: csv_helper.py getfield <csv_file> <BuildFunc> <FieldName>', file=sys.stderr)
            sys.exit(1)
        csv_file = sys.argv[2]
        build_func = sys.argv[3]
        field_name = sys.argv[4]
        get_field(csv_file, build_func, field_name)
    elif cmd == 'delete':
        # Delete a row by BuildFunc
        if len(sys.argv) != 4:
            print('Usage: csv_helper.py delete <csv_file> <BuildFunc>', file=sys.stderr)
            sys.exit(1)
        csv_file = sys.argv[2]
        build_func = sys.argv[3]
        delete_row(csv_file, build_func)
