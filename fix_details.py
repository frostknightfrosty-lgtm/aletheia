with open('app/aletheia/adapters/government_records_us.py', 'r') as f:
    content = f.read()

# Add has_bc_disclosure to the finra details extraction
old_line = '                "bc_disclosure": d.get("hasBcDisclosure"),'
new_line = '''                "bc_disclosure": d.get("hasBcDisclosure"),
                "has_bc_disclosure": d.get("hasBcDisclosure"),'''

content = content.replace(old_line, new_line)

with open('app/aletheia/adapters/government_records_us.py', 'w') as f:
    f.write(content)
print('Done')