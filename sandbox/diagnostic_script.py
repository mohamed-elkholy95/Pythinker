import sys
import pkg_resources

print(f"Python Version: {sys.version}")

print("\nInstalled Packages:")
installed_packages = sorted([f"{p.project_name}=={p.version}" for p in pkg_resources.working_set])
for package in installed_packages:
    print(package)