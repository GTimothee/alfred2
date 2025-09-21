# -*- coding: utf-8 -*-

"""
Ce script scanne toutes les fenêtres ouvertes sur Windows pour identifier
les terminaux Git Bash et extraire leur contexte. Il fournit également des
outils pour exécuter des commandes dans ces contextes et en capturer la sortie.

Dépendances :
pip install pywin32 psutil langchain
"""

import json
import subprocess
import os
import win32gui
import win32process
import psutil
from typing import List, Dict, Any, Optional
from langchain.tools import tool


def convert_mingw_path_to_windows(path: str) -> str:
    """
    Convertit un chemin de style MINGW (ex: '/c/Users/...') en un chemin Windows valide.
    """
    # Supprime le préfixe MINGW64: s'il existe
    if 'MINGW64:' in path:
        path = path.split('MINGW64:', 1)[1]
    
    # Remplace le format /c/ par C:\
    if path.startswith('/'):
        parts = path.split('/')
        if len(parts) > 2 and len(parts[1]) == 1: # ex: ['', 'c', 'Users', ...]
            drive_letter = parts[1].upper()
            windows_path = f"{drive_letter}:\\" + "\\".join(parts[2:])
            return windows_path
            
    return path # Retourne le chemin original s'il n'est pas dans le format attendu


def get_git_bash_windows() -> List[Dict[str, Any]]:
    """
    Scanne les fenêtres et retourne une liste de dictionnaires contenant
    les informations sur les fenêtres Git Bash trouvées.
    Tente d'abord d'obtenir le CWD via psutil, puis se rabat sur l'analyse du titre.
    """
    bash_windows = []

    def enum_windows_callback(hwnd, lParam):  # noqa: D401 unused lParam
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            if "MINGW64" in window_title or window_title.startswith('/'):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid)
                    if process.name().lower() == 'mintty.exe':
                        children = process.children(recursive=True)
                        cwd = "N/A"
                        # Itérer sur les enfants pour trouver un processus bash.exe accessible
                        for child in children:
                            if child.name().lower() == 'bash.exe':
                                try:
                                    possible_cwd = child.cwd()
                                    cwd = possible_cwd
                                    break 
                                except (psutil.AccessDenied, psutil.NoSuchProcess):
                                    if cwd == "N/A":
                                        cwd = "<inaccessible>"
                                    continue
                        
                        # Si psutil a échoué, on essaie de parser le titre comme solution de repli
                        if cwd == "<inaccessible>" or cwd == "N/A":
                           cwd = convert_mingw_path_to_windows(window_title)

                        bash_windows.append({
                            'hwnd': hwnd,
                            'pid': pid,
                            'title': window_title,
                            'cwd': cwd
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

    win32gui.EnumWindows(enum_windows_callback, None)
    return bash_windows


def find_git_bash_path() -> Optional[str]:
    """
    Tente de trouver le chemin de l'exécutable bash.exe de Git.
    C'est une étape cruciale pour l'exécution en arrière-plan.
    """
    # Chemin standard dans Program Files
    possible_path = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Git", "bin", "bash.exe")
    if os.path.exists(possible_path):
        return possible_path
    
    # Chemin standard dans Program Files (x86)
    possible_path_x86 = os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Git", "bin", "bash.exe")
    if os.path.exists(possible_path_x86):
        return possible_path_x86

    # Si on ne le trouve pas, on peut essayer de chercher dans le PATH, mais c'est moins fiable
    # pour cet exemple, nous retournons None.
    print("WARNING: Could not find Git's bash.exe in standard locations.")
    return None


def run_command_in_cwd(cwd: str, command: str) -> Dict[str, Any]:
    """
    Exécute une commande en arrière-plan dans un répertoire de travail (cwd)
    spécifique en utilisant le bash de Git et retourne la sortie.
    """
    git_bash_exe = find_git_bash_path()
    if not git_bash_exe:
        return {"error": "Git Bash executable not found."}

    try:
        # Nous utilisons subprocess.run pour exécuter la commande de manière non-interactive.
        # C'est la méthode la plus robuste pour capturer la sortie.
        result = subprocess.run(
            [git_bash_exe, '-c', command], # '-c' permet de passer une commande au shell bash
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False, # Ne lève pas d'exception si la commande échoue
            encoding='utf-8'
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }

    except FileNotFoundError:
        return {"error": f"Could not find the directory: {cwd}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}


@tool
def get_git_status(cwd: str) -> str:
    """
    Exécute 'git status' dans le répertoire de travail spécifié (cwd) et
    retourne le résultat en JSON.
    """
    output = run_command_in_cwd(cwd, "git status")
    return json.dumps(output, ensure_ascii=False, indent=2)


@tool
def list_git_bash_windows() -> str:
    """
    Retourne une description JSON des fenêtres Git Bash visibles.
    Inclut le handle, le pid, le titre et le répertoire de travail de chaque fenêtre.
    """
    data = get_git_bash_windows()
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print("--- 1. Scanning for open Git Bash windows (for context) ---")
    
    found_windows = get_git_bash_windows()
    
    if not found_windows:
        print("No Git Bash windows found. Cannot run command example.")
    else:
        print(f"Found {len(found_windows)} Git Bash window(s):")
        for i, window in enumerate(found_windows, 1):
            print(f"  - Window {i}: CWD is '{window['cwd']}'")
        
        # --- Démonstration de la nouvelle fonctionnalité ---
        # On prend le répertoire de travail de la première fenêtre trouvée
        target_cwd = found_windows[0]['cwd']
        
        if target_cwd != "N/A" and target_cwd != "<inaccessible>" and os.path.isdir(target_cwd):
            print(f"\n--- 2. Running 'git status' in the context of the first window ('{target_cwd}') ---")
            
            # On exécute la commande et on capture la sortie
            status_result = run_command_in_cwd(target_cwd, "git status")
            
            print("\n--- Command Result ---")
            if status_result.get("error"):
                print(f"Error: {status_result['error']}")
            else:
                print(f"Exit Code: {status_result['returncode']}")
                print("\nSTDOUT:")
                print(status_result['stdout'])
                if status_result['stderr']:
                    print("\nSTDERR:")
                    print(status_result['stderr'])
        else:
            print(f"\nCould not determine a valid working directory ('{target_cwd}') from the open windows to run the command.")

