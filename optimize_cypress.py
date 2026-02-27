import os

file_path = 'new_backend/cypress_executor.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_text = '''            # Install dependencies in the test directory
            print("[CYPRESS] Installing dependencies (cypress-xpath)...")
            install_cmd = "npm install"
            try:
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                proc = subprocess.Popen(
                    install_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                    env=env
                )
                stdout_data, stderr_data = proc.communicate(timeout=60)
                stdout_text = stdout_data.decode('utf-8', errors='replace')
                stderr_text = stderr_data.decode('utf-8', errors='replace')
                
                if proc.returncode != 0:
                    print(f"[CYPRESS] Warning: npm install had issues: {stderr_text[:200]}")
                else:
                    print("[CYPRESS] Dependencies installed successfully")
            except Exception as e:
                print(f"[CYPRESS] Warning: Failed to run npm install: {str(e)}")'''

new_text = '''            # Install dependencies in the test directory (only if needed)
            node_modules_path = os.path.join(test_dir, 'node_modules')
            
            if not os.path.exists(node_modules_path):
                print("[CYPRESS] Installing dependencies (cypress-xpath)...")
                install_cmd = "npm install"
                try:
                    env = os.environ.copy()
                    env['PYTHONIOENCODING'] = 'utf-8'
                    proc = subprocess.Popen(
                        install_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True,
                        env=env
                    )
                    stdout_data, stderr_data = proc.communicate(timeout=60)
                    stdout_text = stdout_data.decode('utf-8', errors='replace')
                    stderr_text = stderr_data.decode('utf-8', errors='replace')
                    
                    if proc.returncode != 0:
                        print(f"[CYPRESS] Warning: npm install had issues: {stderr_text[:200]}")
                    else:
                        print("[CYPRESS] Dependencies installed successfully")
                except Exception as e:
                    print(f"[CYPRESS] Warning: Failed to run npm install: {str(e)}")
            else:
                print("[CYPRESS] Dependencies already installed, skipping npm install (FAST MODE)")'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('[OK] Optimization applied: npm install will be skipped if dependencies exist')
else:
    print('[ERROR] Could not find the exact text to replace')
