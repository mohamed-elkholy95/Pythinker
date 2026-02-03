
import subprocess
import re

def get_mac_specs():
    specs = {}

    # System Version
    try:
        sw_vers = subprocess.check_output(['sw_vers'], text=True)
        for line in sw_vers.splitlines():
            if 'ProductName' in line:
                specs['OS Name'] = line.split(':')[-1].strip()
            elif 'ProductVersion' in line:
                specs['OS Version'] = line.split(':')[-1].strip()
            elif 'BuildVersion' in line:
                specs['OS Build'] = line.split(':')[-1].strip()
    except Exception as e:
        specs['OS Info Error'] = str(e)

    # Hardware Info (using system_profiler)
    try:
        hardware_info = subprocess.check_output(['system_profiler', 'SPHardwareDataType'], text=True)
        for line in hardware_info.splitlines():
            if 'Processor Name' in line:
                specs['CPU'] = line.split(':')[-1].strip()
            elif 'Processor Speed' in line:
                specs['CPU Speed'] = line.split(':')[-1].strip()
            elif 'Number of Processors' in line:
                specs['Number of CPUs'] = line.split(':')[-1].strip()
            elif 'Total Number of Cores' in line:
                specs['Number of Cores'] = line.split(':')[-1].strip()
            elif 'Memory' in line:
                specs['Memory'] = line.split(':')[-1].strip()
            elif 'Model Identifier' in line:
                specs['Model Identifier'] = line.split(':')[-1].strip()
            elif 'Serial Number (system)' in line:
                specs['Serial Number'] = line.split(':')[-1].strip()
            elif 'Boot ROM Version' in line:
                specs['Boot ROM Version'] = line.split(':')[-1].strip()
            elif 'SMC Version (system)' in line:
                specs['SMC Version'] = line.split(':')[-1].strip()
    except Exception as e:
        specs['Hardware Info Error'] = str(e)

    # Graphics Info
    try:
        graphics_info = subprocess.check_output(['system_profiler', 'SPDisplaysDataType'], text=True)
        gpu_names = re.findall(r'Chipset Model: (.+)', graphics_info)
        vram_info = re.findall(r'VRAM \(Total\): (.+)', graphics_info)
        
        if gpu_names:
            specs['Graphics'] = '; '.join([gpu.strip() for gpu in gpu_names])
        if vram_info:
            specs['VRAM'] = '; '.join([vram.strip() for vram in vram_info])
            
    except Exception as e:
        specs['Graphics Info Error'] = str(e)

    # Storage Info
    try:
        storage_info = subprocess.check_output(['system_profiler', 'SPStorageDataType'], text=True)
        disks = []
        current_disk = {}
        for line in storage_info.splitlines():
            if 'Capacity:' in line:
                if current_disk:
                    disks.append(current_disk)
                    current_disk = {}
                current_disk['Capacity'] = line.split(':')[-1].strip()
            elif 'Media Name:' in line:
                current_disk['Media Name'] = line.split(':')[-1].strip()
            elif 'File System:' in line:
                current_disk['File System'] = line.split(':')[-1].strip()
        if current_disk:
            disks.append(current_disk)
        specs['Storage'] = disks
    except Exception as e:
        specs['Storage Info Error'] = str(e)

    return specs

if __name__ == '__main__':
    specs = get_mac_specs()
    for key, value in specs.items():
        if isinstance(value, list):
            print(f"{key}:")
            for item in value:
                print(f"  {item}")
        else:
            print(f"{key}: {value}")
