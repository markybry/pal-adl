import hashlib
import os
import sys


def read_password() -> str:
    # Preferred in debugger/non-interactive runs:
    # 1) Command line arg: python config/generate_password.py "your-password"
    # 2) Env var: PAL_ADL_PASSWORD=your-password
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]

    env_password = os.getenv("PAL_ADL_PASSWORD")
    if env_password:
        return env_password

    if not sys.stdin.isatty():
        print("\n❌ No interactive stdin detected.")
        print("Run with one of these options:")
        print('  - python config/generate_password.py "your-password"')
        print("  - set PAL_ADL_PASSWORD=your-password")
        raise SystemExit(1)

    password = input("\nEnter your desired password: ")
    confirm = input("Confirm password: ")
    if password != confirm:
        print("\n❌ Passwords don't match! Please try again.")
        raise SystemExit(1)

    return password

print("🔐 Password Hash Generator for CQC Dashboard\n")
print("This tool generates a secure hash for your dashboard password.")
print("-" * 60)

password = read_password()

if len(password) < 8:
    print("\n⚠️  Warning: Password is less than 8 characters. Consider using a stronger password.")

# Generate hash
password_hash = hashlib.sha256(password.encode()).hexdigest()

print("\n✅ Password hash generated successfully!")
print("-" * 60)
print(f"\nYour password hash:\n{password_hash}")
print("\n" + "-" * 60)
print("\nNext steps:")
print("1. Create folder: .streamlit/")
print("2. Create file: .streamlit/secrets.toml")
print("3. Add this line to the file:")
print(f'\n   password_hash = "{password_hash}"')
print("\n4. Restart your Streamlit app")
print("\n⚠️  IMPORTANT: Keep this hash private and never commit secrets.toml to git!")
