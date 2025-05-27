import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading
import webbrowser
import json
import os
import wmi
import uuid
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64
import pyperclip
from datetime import datetime, timedelta

try:
    import pygame
    pygame.mixer.init()
    SOUND_AVAILABLE = True
    SPREAD_CHANNEL = pygame.mixer.Channel(0)
    PROFIT_CHANNEL = pygame.mixer.Channel(1)
    SPREAD_ATUAL_CHANNEL = pygame.mixer.Channel(2)
    STARTUP_CHANNEL = pygame.mixer.Channel(3)  # Canal para o som de inicialização
except ImportError:
    print("Erro: Módulo pygame não instalado. Alertas sonoros desativados.")
    SOUND_AVAILABLE = False
    SPREAD_CHANNEL = None
    PROFIT_CHANNEL = None
    SPREAD_ATUAL_CHANNEL = None
    STARTUP_CHANNEL = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALERT_SOUND_PATH = os.path.join(SCRIPT_DIR, "Alerta1.wav")
EAGAINS_SOUND_PATH = os.path.join(SCRIPT_DIR, "Alerta2.wav")
STARTUP_SOUND_PATH = os.path.join(SCRIPT_DIR, "Abertura.wav")  # Caminho para o som de inicialização
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
VALIDATION_FILE = os.path.join(SCRIPT_DIR, "validated.key")

GITHUB_LICENSE_URL = "https://raw.githubusercontent.com/Yaohusaf/Raz-o/main/Seriais.txt"

root = tk.Tk()
root.title("Monitor de Arbitragem")
root.geometry("800x600")
root.resizable(False, False)

# Centralizar a janela na tela
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
window_width = 800
window_height = 600
x_position = (screen_width - window_width) // 2
y_position = (screen_height - window_height) // 2
root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

api_spot_price = "https://api.mexc.com/api/v3/ticker/bookTicker"
api_spot_volume = "https://api.mexc.com/api/v3/ticker/24hr"
api_futures = "https://contract.mexc.com/api/v1/contract/ticker"
opportunities_base_url = "https://www.mexc.com/pt-PT/exchange/"

SPOT_BASE_URL = "https://www.mexc.com/pt-PT/exchange/"
FUTUROS_BASE_URL = "https://futures.mexc.com/pt-PT/exchange/"

tempo_atualizacao = 5000  
min_spread_padrao = 0.5
max_spread_padrao = 1.5
min_volume_padrao = 50_000
max_volume_padrao = 1_000_000_000
min_count_threshold_padrao = 0
max_count_threshold_padrao = 100
janela_no_topo_padrao = False
top5_tempo_minutos_padrao = 5
top5_num_itens_padrao = 5
monitor_tempo_atualizacao_padrao = 1000
monitor_position_right_padrao = True
monitor_position_left_padrao = False
profit_alert_minimo_padrao = 0.9
spread_atual_alert_minimo_padrao = 1.0
advanced_topmost_padrao = False
monitor_topmost_padrao = False
inversion_window_minutes_padrao = 5  

top5_contagem = {}
top5_start_time = None
top5_tempo_minutos_segundos = top5_tempo_minutos_padrao * 60
MAX_COUNT_THRESHOLD = max_count_threshold_padrao

# Ajuste no spread_history para manter histórico persistente
spread_history = {}  # Agora será um dicionário {ativo: [(timestamp, spread), ...]}
INVERSION_WINDOW = timedelta(minutes=inversion_window_minutes_padrao)

monitor_window = None
advanced_config_window = None

janela_no_topo_var = tk.BooleanVar(value=janela_no_topo_padrao)
advanced_topmost_var = tk.BooleanVar(value=advanced_topmost_padrao)
monitor_topmost_var = tk.BooleanVar(value=monitor_topmost_padrao)
mexc_enabled_var = tk.BooleanVar(value=True)
monitor_position_right_var = tk.BooleanVar(value=monitor_position_right_padrao)
monitor_position_left_var = tk.BooleanVar(value=monitor_position_left_padrao)

top5_tempo_minutos = top5_tempo_minutos_padrao
top5_num_itens = top5_num_itens_padrao
monitor_tempo_atualizacao = monitor_tempo_atualizacao_padrao
inversion_window_minutes = inversion_window_minutes_padrao
min_count_threshold = min_count_threshold_padrao
max_count_threshold = max_count_threshold_padrao

cached_spot_data = None
cached_futuros_data = None
last_fetch_time = None
CACHE_DURATION = 2

update_id = None

def get_machine_ident():
    try:
        c = wmi.WMI()
        for disk in c.Win32_DiskDrive():
            serial_number = disk.SerialNumber.strip()
            if serial_number:
                break
        else:
            serial_number = "unknown_disk_serial"
    except Exception as e:
        print(f"Erro ao obter número de série do disco: {e}")
        serial_number = "unknown_disk_serial"

    try:
        mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0, 8*6, 8)][::-1])
    except Exception as e:
        print(f"Erro ao obter endereço MAC: {e}")
        mac_address = "unknown_mac_address"

    combined = f"{serial_number}:{mac_address}".encode()
    machine_hash = hashlib.sha256(combined).hexdigest()
    print(f"Hash da máquina gerado: {machine_hash}")
    return machine_hash

def is_machine_validated():
    return os.path.exists(VALIDATION_FILE)

def mark_machine_validated():
    with open(VALIDATION_FILE, 'w') as f:
        f.write(get_machine_ident())

def check_github_license():
    try:
        response = requests.get(GITHUB_LICENSE_URL, timeout=5)
        response.raise_for_status()
        content = response.text.strip()
        if not content:
            print("Arquivo Seriais.txt está vazio.")
            messagebox.showerror("Erro de Licença", "O arquivo Seriais.txt no GitHub está vazio.")
            return False

        lines = content.splitlines()
        machine_hash = get_machine_ident()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith(machine_hash + ":"):
                print(f"Chave válida encontrada para hash da máquina: {machine_hash}")
                mark_machine_validated()
                return True
        print(f"Nenhuma chave válida encontrada para hash da máquina: {machine_hash}")
        messagebox.showerror("Erro de Licença", "Nenhuma chave válida encontrada no GitHub para esta máquina. Verifique o repositório ou gere uma nova chave.")
        return False
    except Exception as e:
        print(f"Erro ao verificar a licença no GitHub: {e}")
        messagebox.showerror("Erro", f"Falha ao verificar a licença no GitHub: {e}")
        return False

def generate_key_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    print(f"Chave mestra gerada: {key}")
    return key, salt

def save_encrypted_key(password):
    try:
        machine_hash = get_machine_ident()
        print(f"Hash da máquina: {machine_hash}")
        master_key, salt = generate_key_password(password)
        print(f"Master key: {master_key}, Salt: {salt}")
        fernet = Fernet(master_key)
        print("Fernet inicializado para criptografia.")
        aes_key = Fernet.generate_key().decode()
        print(f"Chave AES gerada: {aes_key}")
        data_to_encrypt = f"{aes_key}:{machine_hash}"
        print(f"Dados a serem criptografados: {data_to_encrypt}")
        encrypted_data = fernet.encrypt(data_to_encrypt.encode())
        print(f"Dados criptografados: {encrypted_data}")
        license_content = base64.b64encode(salt + encrypted_data).decode()
        full_key = f"{machine_hash}:{license_content}"
        print(f"Chave para o GitHub Gerada: {full_key}")
        return full_key, None
    except Exception as e:
        print(f"Falha ao criar a chave: {e}")
        return None, str(e)

def verify_login():
    if is_machine_validated():
        root.deiconify()
        return

    login_window = tk.Toplevel(root)
    login_window.title("Chave Criptografada")
    login_window.geometry("400x350")
    login_window.resizable(False, False)

    password = "M3uC0mpuT@d0r2025!"
    license_content, error = save_encrypted_key(password)

    if error:
        print(f"Erro ao gerar a chave: {error}")
        login_window.destroy()
        root.quit()
        return

    ttk.Label(login_window, text="Chave Criptografada Gerada:", font=("Arial", 12, "bold")).pack(pady=20)
    output_text = tk.Text(login_window, height=4, width=40)
    output_text.pack(pady=10)
    output_text.insert(tk.END, f"Chave para o GitHub:\n{license_content}\n\nInstruções:\n1. Acesse o repositório: https://github.com/Yaohusaf/Raz-o\n2. Edite o arquivo 'Seriais.txt'.\n3. Adicione esta chave em uma nova linha.\n4. Faça commit e push das alterações.\n5. Clique em 'Continuar' para validar.")
    output_text.config(state="disabled")

    ttk.Button(login_window, text="Copiar Chave", command=lambda: pyperclip.copy(license_content)).pack(pady=5)

    def proceed():
        if check_github_license():
            login_window.destroy()
            root.deiconify()
        else:
            messagebox.showwarning("Aviso", "A chave no GitHub não foi validada. Certifique-se de que a chave foi adicionada corretamente ao Seriais.txt.")

    ttk.Button(login_window, text="Continuar", command=proceed).pack(pady=5)

    login_window.protocol("WM_DELETE_WINDOW", lambda: root.quit())
    root.withdraw()

def salvar_configuracoes():
    global top5_start_time, top5_num_itens, top5_tempo_minutos_segundos, INVERSION_WINDOW, inversion_window_minutes, min_count_threshold, max_count_threshold
    config = {
        "min_spread": min_spread_padrao,
        "max_spread": max_spread_padrao,
        "min_volume": min_volume_padrao,
        "max_volume": max_volume_padrao,
        "min_count_threshold": min_count_threshold,
        "max_count_threshold": max_count_threshold,
        "tempo_atualizacao": tempo_atualizacao / 1000,
        "janela_no_topo": janela_no_topo_var.get(),
        "top5_tempo_minutos": top5_tempo_minutos,
        "top5_num_itens": top5_num_itens,
        "monitor_tempo_atualizacao": monitor_tempo_atualizacao / 1000,
        "monitor_position_right": monitor_position_right_var.get(),
        "monitor_position_left": monitor_position_left_var.get(),
        "profit_alert_minimo": profit_alert_minimo_padrao,
        "spread_atual_alert_minimo": spread_atual_alert_minimo_padrao,
        "api_spot_price": api_spot_price,
        "api_spot_volume": api_spot_volume,
        "api_futures": api_futures,
        "spot_base_url": SPOT_BASE_URL,
        "futuros_base_url": FUTUROS_BASE_URL,
        "opportunities_base_url": opportunities_base_url,
        "advanced_topmost": advanced_topmost_var.get(),
        "monitor_topmost": monitor_topmost_var.get(),
        "mexc_enabled": mexc_enabled_var.get(),
        "inversion_window_minutes": inversion_window_minutes
    }
    try:
        os.makedirs(SCRIPT_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        top5_start_time = datetime.now()
        top5_tempo_minutos_segundos = top5_tempo_minutos * 60
        INVERSION_WINDOW = timedelta(minutes=inversion_window_minutes)
        tree.heading("Inversões", text=f"Inversões ({int(inversion_window_minutes)}m)")
        top5_tree.heading("Inversões", text=f"Inversões ({int(inversion_window_minutes)}m)")
        frame_top5.config(text=f"Top {top5_num_itens} Spreads mais Elevados")
    except Exception as e:
        print(f"Erro ao salvar configurações: {e}")

def carregar_configuracoes():
    global tempo_atualizacao, min_spread_padrao, max_spread_padrao, min_volume_padrao, max_volume_padrao, janela_no_topo_padrao, top5_tempo_minutos_padrao, top5_num_itens_padrao, monitor_tempo_atualizacao_padrao, monitor_position_right_padrao, monitor_position_left_padrao, profit_alert_minimo_padrao, spread_atual_alert_minimo_padrao, api_spot_price, api_spot_volume, api_futures, SPOT_BASE_URL, FUTUROS_BASE_URL, opportunities_base_url, advanced_topmost_padrao, monitor_topmost_padrao, inversion_window_minutes_padrao, inversion_window_minutes, INVERSION_WINDOW, min_count_threshold_padrao, max_count_threshold_padrao, min_count_threshold, max_count_threshold
    if not os.path.exists(CONFIG_FILE):
        print(f"Arquivo {CONFIG_FILE} não encontrado. Criando um novo com valores padrão...")
        salvar_configuracoes()
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            min_spread_padrao = float(config.get("min_spread", min_spread_padrao))
            max_spread_padrao = float(config.get("max_spread", max_spread_padrao))
            min_volume_padrao = float(config.get("min_volume", min_volume_padrao))
            max_volume_padrao = float(config.get("max_volume", max_volume_padrao))
            min_count_threshold = float(config.get("min_count_threshold", min_count_threshold_padrao))
            max_count_threshold = float(config.get("max_count_threshold", max_count_threshold_padrao))
            tempo_atualizacao = int(float(config.get("tempo_atualizacao", tempo_atualizacao / 1000)) * 1000)
            janela_no_topo_padrao = config.get("janela_no_topo", janela_no_topo_padrao)
            top5_tempo_minutos_padrao = float(config.get("top5_tempo_minutos", top5_tempo_minutos_padrao))
            top5_num_itens_padrao = int(config.get("top5_num_itens", top5_num_itens_padrao))
            monitor_tempo_atualizacao_padrao = int(float(config.get("monitor_tempo_atualizacao", monitor_tempo_atualizacao_padrao / 1000)) * 1000)
            monitor_position_right_padrao = config.get("monitor_position_right", monitor_position_right_padrao)
            monitor_position_left_padrao = config.get("monitor_position_left", monitor_position_left_padrao)
            profit_alert_minimo_padrao = float(config.get("profit_alert_minimo", profit_alert_minimo_padrao))
            spread_atual_alert_minimo_padrao = float(config.get("spread_atual_alert_minimo", spread_atual_alert_minimo_padrao))
            api_spot_price = config.get("api_spot_price", api_spot_price)
            api_spot_volume = config.get("api_spot_volume", api_spot_volume)
            api_futures = config.get("api_futures", api_futures)
            SPOT_BASE_URL = config.get("spot_base_url", SPOT_BASE_URL)
            FUTUROS_BASE_URL = config.get("futuros_base_url", FUTUROS_BASE_URL)
            opportunities_base_url = config.get("opportunities_base_url", opportunities_base_url)
            advanced_topmost_padrao = config.get("advanced_topmost", advanced_topmost_padrao)
            monitor_topmost_padrao = config.get("monitor_topmost", monitor_topmost_padrao)
            inversion_window_minutes_padrao = float(config.get("inversion_window_minutes", inversion_window_minutes_padrao))
            janela_no_topo_var.set(janela_no_topo_padrao)
            advanced_topmost_var.set(advanced_topmost_padrao)
            monitor_topmost_var.set(monitor_topmost_padrao)
            mexc_enabled_var.set(config.get("mexc_enabled", True))
            monitor_position_right_var.set(monitor_position_right_padrao)
            monitor_position_left_var.set(monitor_position_left_padrao)
            inversion_window_minutes = inversion_window_minutes_padrao
            INVERSION_WINDOW = timedelta(minutes=inversion_window_minutes)
            min_count_threshold = min_count_threshold
            max_count_threshold = max_count_threshold
    except Exception as e:
        print(f"Erro ao carregar configurações: {e}")
        salvar_configuracoes()
    return {
        "min_spread": min_spread_padrao,
        "max_spread": max_spread_padrao,
        "min_volume": min_volume_padrao / 1_000_000,
        "max_volume": max_volume_padrao / 1_000_000,
        "min_count_threshold": min_count_threshold,
        "max_count_threshold": max_count_threshold,
        "tempo_atualizacao": tempo_atualizacao / 1000,
        "janela_no_topo": janela_no_topo_var.get(),
        "top5_tempo_minutos": top5_tempo_minutos_padrao,
        "top5_num_itens": top5_num_itens_padrao,
        "monitor_tempo_atualizacao": monitor_tempo_atualizacao_padrao / 1000,
        "monitor_position_right": monitor_position_right_padrao,
        "monitor_position_left": monitor_position_left_padrao,
        "profit_alert_minimo": profit_alert_minimo_padrao,
        "spread_atual_alert_minimo": spread_atual_alert_minimo_padrao,
        "api_spot_price": api_spot_price,
        "api_spot_volume": api_spot_volume,
        "api_futures": api_futures,
        "spot_base_url": SPOT_BASE_URL,
        "futuros_base_url": FUTUROS_BASE_URL,
        "opportunities_base_url": opportunities_base_url,
        "advanced_topmost": advanced_topmost_var.get(),
        "monitor_topmost": monitor_topmost_var.get(),
        "mexc_enabled": mexc_enabled_var.get(),
        "inversion_window_minutes": inversion_window_minutes
    }

def formatar_volume(valor):
    try:
        valor = float(valor)
        if valor >= 1_000_000:
            return f"{valor / 1_000_000:.2f}M"
        elif valor >= 1_000:
            return f"{valor / 1_000:.2f}K"
        else:
            return f"{valor:.2f}"
    except (ValueError, TypeError):
        return "0.00"

def formatar_tempo_regressivo(segundos):
    minutos = int(segundos // 60)
    segundos_restantes = int(segundos % 60)
    return f"Contagem ({minutos:02d}:{segundos_restantes:02d})"

def atualizar_data_hora():
    now = datetime.now()
    data_hora_atual = now.strftime("%d/%m/%y - %H:%M:%S")
    label_data_hora.config(text=data_hora_atual)
    root.after(1000, atualizar_data_hora)

def atualizar_contagem_regressiva():
    global top5_start_time, top5_tempo_minutos_segundos
    if top5_start_time is None:
        top5_start_time = datetime.now()
    current_time = datetime.now()
    elapsed_time = (current_time - top5_start_time).total_seconds()
    remaining_time = max(0, top5_tempo_minutos_segundos - elapsed_time)
    top5_tree.heading("#5", text=formatar_tempo_regressivo(remaining_time))
    root.after(1000, atualizar_contagem_regressiva)

def obter_preco_spot():
    global api_spot_price, api_spot_volume
    try:
        response_preco = requests.get(api_spot_price, timeout=5)
        response_preco.raise_for_status()
        dados_preco = response_preco.json()
        if not isinstance(dados_preco, list):
            print("Resposta inválida da API Spot bookTicker. Esperava uma lista, mas recebeu:", dados_preco)
            return {}
        precos = {}
        for item in dados_preco:
            symbol = item.get("symbol")
            ask_price = item.get("askPrice")
            if ask_price and ask_price != "0":
                precos[symbol] = round(float(ask_price), 6)
            else:
                precos[symbol] = 0.0

        response_volume = requests.get(api_spot_volume, timeout=5)
        response_volume.raise_for_status()
        dados_volume = response_volume.json()
        volumes = {item["symbol"]: float(item.get("volume", 0)) for item in dados_volume}

        spot_dict = {}
        for symbol in precos:
            spot_dict[symbol] = {
                "price": precos[symbol],
                "volume": volumes.get(symbol, 0)
            }
        return spot_dict
    except Exception as e:
        print(f"Erro ao obter dados Spot: {e}")
        return {}

def obter_preco_futuros():
    global api_futures
    try:
        response_futuros = requests.get(api_futures, timeout=5)
        response_futuros.raise_for_status()
        data_futuros = response_futuros.json().get("data", [])

        futuros_dict = {}
        for item in data_futuros:
            symbol = item["symbol"]
            spot_symbol = symbol.replace("_USDT", "USDT")
            bid1 = item.get("bid1")
            if bid1 and bid1 != "0":
                futuros_dict[spot_symbol] = {
                    "price": round(float(bid1), 6),
                    "volume": round(float(item.get("volume24", 0)), 2),
                    "funding_rate": round(float(item.get("fundingRate", 0)) * 100, 4),
                    "original_symbol": symbol
                }
            else:
                futuros_dict[spot_symbol] = {
                    "price": 0.0,
                    "volume": round(float(item.get("volume24", 0)), 2),
                    "funding_rate": round(float(item.get("fundingRate", 0)) * 100, 4),
                    "original_symbol": symbol
                }
        return futuros_dict
    except Exception as e:
        print(f"Erro ao obter dados Futuros: {e}")
        return {}

def calcular_inversoes(ativo, current_time):
    if ativo not in spread_history:
        spread_history[ativo] = []
        return 0

    # Filtrar o histórico dentro da janela de inversões
    spread_history[ativo] = [(t, s) for t, s in spread_history[ativo] if current_time - t <= INVERSION_WINDOW]
    if len(spread_history[ativo]) < 2:
        return 0

    inversoes = 0
    for i in range(1, len(spread_history[ativo])):
        prev_spread = spread_history[ativo][i-1][1]
        curr_spread = spread_history[ativo][i][1]
        if (prev_spread >= 0 and curr_spread < 0) or (prev_spread < 0 and curr_spread >= 0):
            inversoes += 1
    return inversoes

def fetch_data_async(callback):
    global cached_spot_data, cached_futuros_data, last_fetch_time
    def fetch():
        nonlocal spot_data, futuros_data
        spot_data = obter_preco_spot()
        futuros_data = obter_preco_futuros()
        cached_spot_data = spot_data
        cached_futuros_data = futuros_data
        last_fetch_time = datetime.now()
        root.after(0, callback, spot_data, futuros_data)

    current_time = datetime.now()
    if (last_fetch_time is None or 
        (current_time - last_fetch_time).total_seconds() > CACHE_DURATION or 
        cached_spot_data is None or 
        cached_futuros_data is None):
        spot_data = {}
        futuros_data = {}
        threading.Thread(target=fetch, daemon=True).start()
    else:
        callback(cached_spot_data, cached_futuros_data)

def fetch_data_for_monitor():
    global cached_spot_data, cached_futuros_data, last_fetch_time
    current_time = datetime.now()
    if (last_fetch_time is None or 
        (current_time - last_fetch_time).total_seconds() > CACHE_DURATION or 
        cached_spot_data is None or 
        cached_futuros_data is None):
        spot_data = obter_preco_spot()
        futuros_data = obter_preco_futuros()
        cached_spot_data = spot_data
        cached_futuros_data = futuros_data
        last_fetch_time = current_time
        return spot_data, futuros_data
    return cached_spot_data, cached_futuros_data

config_inicial = carregar_configuracoes()
top5_tempo_minutos = config_inicial["top5_tempo_minutos"]
top5_num_itens = config_inicial["top5_num_itens"]
monitor_tempo_atualizacao = config_inicial["monitor_tempo_atualizacao"] * 1000
inversion_window_minutes = config_inicial["inversion_window_minutes"]
INVERSION_WINDOW = timedelta(minutes=inversion_window_minutes)
min_count_threshold = config_inicial["min_count_threshold"]
max_count_threshold = config_inicial["max_count_threshold"]

notebook = ttk.Notebook(root)
tab_scanner = ttk.Frame(notebook)
tab_config = ttk.Frame(notebook)
notebook.add(tab_scanner, text="Scanner")
notebook.add(tab_config, text="Configurações Simples")
notebook.pack(expand=True, fill="both")

style = ttk.Style()
style.configure("Modern.TFrame", background="#F8F9FA")
style.configure("Modern.TLabelframe", background="#FFFFFF", foreground="#1A73E8", relief="flat")
style.configure("Modern.TLabelframe.Label", font=("Segoe UI", 14, "bold"), foreground="#1A73E8")
style.configure("Modern.TCheckbutton", background="#FFFFFF", foreground="#333333", font=("Segoe UI", 11))
style.configure("Modern.TButton", background="#1A73E8", foreground="#000000", font=("Segoe UI", 11, "bold"))
style.map("Modern.TButton", 
          background=[('active', '#1557B0')],
          foreground=[('active', '#000000')])
style.configure("Modern.TEntry", fieldbackground="#E8F0FE", foreground="#333333", bordercolor="#1A73E8", relief="flat")
style.configure("Modern.TLabel", background="#F8F9FA", foreground="#333333", font=("Segoe UI", 11))

style.configure("Modern.Treeview", font=("Segoe UI", 10), rowheight=25, fieldbackground="#FFFFFF", bordercolor="#D3D3D3", relief="flat")
style.configure("Modern.Treeview.Heading", font=("Segoe UI", 11, "bold"), background="#E8F0FE", foreground="#1A73E8", bordercolor="#D3D3D3", relief="flat")
style.map("Modern.Treeview", background=[('selected', '#E8F0FE')], foreground=[('selected', '#1A73E8')])
style.map("Modern.Treeview.Heading", background=[('active', '#D3E3FD')])

frame_scanner = ttk.Frame(tab_scanner, padding=20, style="Modern.TFrame")
frame_scanner.pack(fill="both", expand=True)

label_data_hora = ttk.Label(frame_scanner, text="27/05/25 - 01:12:00", font=("Segoe UI", 12, "bold"), foreground="#1A73E8", style="Modern.TLabel")
label_data_hora.pack(anchor="nw", pady=(0, 10))

frame_tree = ttk.LabelFrame(frame_scanner, text="Lista de Ativos", padding=5, style="Modern.TLabelframe")
frame_tree.pack(fill="both", expand=True)

columns = ("Ativo", "Preço Spot", "Preço Futuros", "Spread", "Volume", "Inversões", "Funding Rate")
tree = ttk.Treeview(frame_tree, columns=columns, show="headings", style="Modern.Treeview", height=8)
for col in columns:
    tree.heading(col, text=col)
    tree.column(col, anchor="center", 
                width=100 if col == "Ativo" else 
                90 if col in ["Preço Futuros", "Inversões", "Funding Rate"] else 
                100 if col == "Volume" else 
                70)
tree.column("Inversões", width=100)
tree.tag_configure("negativo", foreground="#FF0000")
tree.tag_configure("positivo", foreground="#006400")
tree.tag_configure("negative_funding", foreground="#FF0000")
tree.tag_configure("mensagem", foreground="#1A73E8", font=("Segoe UI", 12, "italic"))
tree.heading("Inversões", text=f"Inversões ({int(inversion_window_minutes)}m)")
tree.pack(fill="both", expand=True)

frame_top5 = ttk.LabelFrame(frame_scanner, text=f"Top {top5_num_itens} Spreads mais Elevados", padding=5, style="Modern.TLabelframe")
frame_top5.pack(fill="both", pady=(5, 0))

top5_columns = ("Rank", "Par", "Rota", "Spread", "Contagem", "Inversões")
top5_tree = ttk.Treeview(frame_top5, columns=top5_columns, show="headings", style="Modern.Treeview", height=5)
for col in top5_columns:
    top5_tree.heading(col, text=col)
    top5_tree.column(col, anchor="center", width=40 if col == "Rank" else 80 if col == "Par" else 150 if col == "Rota" else 100 if col == "Contagem" else 100 if col == "Inversões" else 60)
top5_tree.tag_configure("negativo", foreground="#FF0000")
top5_tree.tag_configure("positivo", foreground="#006400")
top5_tree.heading("Inversões", text=f"Inversões ({int(inversion_window_minutes)}m)")
top5_tree.pack(fill="both", expand=True)

def abrir_monitoramento_on_double_click(event, tree_widget):
    try:
        selected_item = tree_widget.selection()
        if not selected_item:
            return
        ativo = tree_widget.item(selected_item[0])['values'][0] if tree_widget == tree else tree_widget.item(selected_item[0])['values'][1]
        if ativo == "Erro" or ativo == "Aviso" or ativo == "N/A" or ativo == "Nenhuma corretora selecionada para análise de dados.":
            return
        abrir_monitoramento()
    except Exception as e:
        print(f"Erro ao abrir monitoramento: {e}")

tree.bind("<Double-1>", lambda e: abrir_monitoramento_on_double_click(e, tree))
top5_tree.bind("<Double-1>", lambda e: abrir_monitoramento_on_double_click(e, top5_tree))

def parar_som():
    if SOUND_AVAILABLE:
        if SPREAD_CHANNEL.get_busy():
            SPREAD_CHANNEL.stop()
        if PROFIT_CHANNEL.get_busy():
            PROFIT_CHANNEL.stop()
        if SPREAD_ATUAL_CHANNEL.get_busy():
            SPREAD_ATUAL_CHANNEL.stop()
        if STARTUP_CHANNEL.get_busy():
            STARTUP_CHANNEL.stop()

def abrir_monitoramento():
    global monitor_window, spread_history
    if monitor_window is not None and monitor_window.winfo_exists():
        monitor_window.destroy()

    ativo = None
    spot_price = None
    futuros_price = None
    if tree.selection():
        selected_item = tree.selection()[0]
        ativo = tree.item(selected_item)['values'][0]
        spot_price = tree.item(selected_item)['values'][1]
        futuros_price = tree.item(selected_item)['values'][2]
    elif top5_tree.selection():
        selected_item = top5_tree.selection()[0]
        ativo = top5_tree.item(selected_item)['values'][1]
        for item in tree.get_children():
            if tree.item(item)['values'][0] == ativo:
                spot_price = tree.item(item)['values'][1]
                futuros_price = tree.item(item)['values'][2]
                break
        if spot_price is None or futuros_price is None:
            spot_data, futuros_data = fetch_data_for_monitor()
            if ativo in spot_data and ativo in futuros_data:
                spot_price = spot_data[ativo]["price"]
                futuros_price = futuros_data[ativo]["price"]

    if not ativo or spot_price is None or futuros_price is None:
        messagebox.showerror("Erro", "Não foi possível obter os dados do ativo selecionado.")
        return

    monitor_window = tk.Toplevel(root)
    monitor_window.title(f"Monitor: {ativo} (MEXC Spot / MEXC Futuros)")
    monitor_window.geometry("500x550")
    root_x = root.winfo_x()
    root_y = root.winfo_y()
    root_width = root.winfo_width()
    monitor_width = 500
    if monitor_position_right_var.get():
        monitor_window.geometry(f"+{root_x + root_width}+{root_y}")
    elif monitor_position_left_var.get():
        monitor_window.geometry(f"+{root_x - monitor_width}+{root_y}")
    else:
        monitor_window.geometry(f"+{root_x + root_width}+{root_y}")

    monitor_window.resizable(False, False)
    monitor_window.attributes('-topmost', monitor_topmost_var.get())

    monitor_tempo_atualizacao_var = tk.DoubleVar(value=monitor_tempo_atualizacao_padrao / 1000)

    monitor_notebook = ttk.Notebook(monitor_window)
    tab_calculadora = ttk.Frame(monitor_notebook)
    tab_monitor_config = ttk.Frame(monitor_notebook)
    monitor_notebook.add(tab_calculadora, text="Calculadora Arb")
    monitor_notebook.add(tab_monitor_config, text="Configurações")
    monitor_notebook.pack(expand=True, fill="both", padx=5, pady=5)

    frame_principal = ttk.LabelFrame(tab_calculadora, text="Principal", padding=5)
    frame_principal.pack(fill="both", expand=True, padx=5, pady=5)

    ttk.Label(frame_principal, text=f"Par [{ativo}]:", font=("Helvetica", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
    ttk.Label(frame_principal, text=ativo).grid(row=0, column=1, sticky="w", padx=5, pady=2)

    ttk.Label(frame_principal, text="Rota:", font=("Helvetica", 10, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=2)
    ttk.Label(frame_principal, text="MEXC Spot / MEXC Futuros").grid(row=1, column=1, sticky="w", padx=5, pady=2)

    spot_price_value = float(spot_price)
    futuros_price_value = float(futuros_price)

    ttk.Label(frame_principal, text="Preço compra ENTRADA (MEXC Spot):", font=("Helvetica", 10, "bold")).grid(row=2, column=0, sticky="w", padx=5, pady=2)
    entry_spot_price = ttk.Entry(frame_principal, width=15)
    entry_spot_price.insert(0, f"{spot_price_value:.6f}")
    entry_spot_price.grid(row=2, column=1, sticky="w", padx=5, pady=2)

    ttk.Label(frame_principal, text="Preço venda ENTRADA (MEXC Futuros):", font=("Helvetica", 10, "bold")).grid(row=3, column=0, sticky="w", padx=5, pady=2)
    entry_futuros_price = ttk.Entry(frame_principal, width=15)
    entry_futuros_price.insert(0, f"{futuros_price_value:.6f}")
    entry_futuros_price.grid(row=3, column=1, sticky="w", padx=5, pady=2)

    def update_entry_spread():
        try:
            spot = float(entry_spot_price.get())
            futuros = float(entry_futuros_price.get())
            if spot > 0:
                spread = ((futuros - spot) / spot) * 100
                label_entry_spread.config(text=f"{spread:.2f}%")
            else:
                label_entry_spread.config(text="0.00%")
        except:
            label_entry_spread.config(text="Erro")

    ttk.Label(frame_principal, text="SPREAD GARANTIDO NA ENTRADA (%):", font=("Helvetica", 10, "bold")).grid(row=4, column=0, sticky="w", padx=5, pady=2)
    label_entry_spread = ttk.Label(frame_principal, text="0.00%")
    label_entry_spread.grid(row=4, column=1, sticky="w", padx=5, pady=2)

    current_time = datetime.now()
    inversoes = calcular_inversoes(ativo, current_time)

    ttk.Label(frame_principal, text=f"INVERSÕES ({int(inversion_window_minutes)}m):", font=("Helvetica", 10, "bold")).grid(row=5, column=0, sticky="w", padx=5, pady=2)
    label_inversoes = ttk.Label(frame_principal, text=str(inversoes))
    label_inversoes.grid(row=5, column=1, sticky="w", padx=5, pady=2)

    entry_spot_price.bind("<KeyRelease>", lambda e: update_entry_spread())
    entry_futuros_price.bind("<KeyRelease>", lambda e: update_entry_spread())
    update_entry_spread()

    frame_buttons = ttk.Frame(frame_principal)
    frame_buttons.grid(row=7, column=0, columnspan=2, pady=10)

    ttk.Button(frame_buttons, text="Parar Monitoramento", command=monitor_window.destroy).pack(side="left", padx=5)
    ttk.Button(frame_buttons, text="Abrir Links", command=lambda: [
        webbrowser.open_new_tab(f"{FUTUROS_BASE_URL}{ativo.replace('USDT', '_USDT')}"),
        webbrowser.open_new_tab(f"{SPOT_BASE_URL}{ativo.replace('USDT', '_USDT')}")
    ]).pack(side="left", padx=5)

    frame_monitor = ttk.LabelFrame(tab_calculadora, text="Monitoramento de Par em Tempo Real", padding=5)
    frame_monitor.pack(fill="both", expand=True, padx=5, pady=5)

    ttk.Label(frame_monitor, text="Preço compra (MEXC Spot):", font=("Helvetica", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
    label_current_spot = ttk.Label(frame_monitor, text=f"{spot_price_value:.6f}", foreground="#006400")
    label_current_spot.grid(row=0, column=1, sticky="w", padx=5, pady=2)

    ttk.Label(frame_monitor, text="Preço venda (MEXC Futuros):", font=("Helvetica", 10, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=2)
    label_current_futuros = ttk.Label(frame_monitor, text=f"{futuros_price_value:.6f}", foreground="#006400")
    label_current_futuros.grid(row=1, column=1, sticky="w", padx=5, pady=2)

    ttk.Label(frame_monitor, text="SPREAD ATUAL DO PAR (%):", font=("Helvetica", 10, "bold")).grid(row=2, column=0, sticky="w", padx=5, pady=2)
    label_current_spread = ttk.Label(frame_monitor, text="0.00%", background="#FFFFFF")
    label_current_spread.grid(row=2, column=1, sticky="w", padx=5, pady=2)

    spread_alert_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame_monitor, text="Alerta ≥", variable=spread_alert_var, command=lambda: SPREAD_ATUAL_CHANNEL.stop() if not spread_alert_var.get() else None).grid(row=2, column=2, padx=5, pady=2)
    entry_spread_alert = ttk.Entry(frame_monitor, width=5)
    entry_spread_alert.insert(0, str(spread_atual_alert_minimo_padrao))
    entry_spread_alert.grid(row=2, column=3, padx=5, pady=2)

    ttk.Label(frame_monitor, text="LUCRO TOTAL (%):", font=("Helvetica", 10, "bold")).grid(row=3, column=0, sticky="w", padx=5, pady=2)
    label_profit = ttk.Label(frame_monitor, text="0.00%", foreground="#FF0000", background="#FFFFFF")
    label_profit.grid(row=3, column=1, sticky="w", padx=5, pady=2)

    profit_alert_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame_monitor, text="Alerta ≥", variable=profit_alert_var, command=lambda: PROFIT_CHANNEL.stop() if not profit_alert_var.get() else None).grid(row=3, column=2, padx=5, pady=2)
    entry_profit_alert = ttk.Entry(frame_monitor, width=5)
    entry_profit_alert.insert(0, str(profit_alert_minimo_padrao))
    entry_profit_alert.grid(row=3, column=3, padx=5, pady=2)

    ttk.Label(frame_monitor, text="Próxima Funding Rate:", font=("Helvetica", 10, "bold")).grid(row=4, column=0, sticky="w", padx=5, pady=2)
    label_next_funding = ttk.Label(frame_monitor, text="Calculando...")
    label_next_funding.grid(row=4, column=1, sticky="w", padx=5, pady=2)

    ttk.Label(frame_monitor, text="Cont. Regressiva:", font=("Helvetica", 10, "bold")).grid(row=5, column=0, sticky="w", padx=5, pady=2)
    label_funding_countdown = ttk.Label(frame_monitor, text="Calculando...")
    label_funding_countdown.grid(row=5, column=1, sticky="w", padx=5, pady=2)

    if ativo not in top5_contagem:
        top5_contagem[ativo] = [0, current_time]
    contagem = top5_contagem[ativo][0]

    ttk.Label(frame_principal, text="CONTAGEM:", font=("Helvetica", 10, "bold")).grid(row=6, column=0, sticky="w", padx=5, pady=2)
    label_contagem = ttk.Label(frame_principal, text=f"{int(contagem)}s")
    label_contagem.grid(row=6, column=1, sticky="w", padx=5, pady=2)

    frame_config_monitor = ttk.Frame(tab_monitor_config, padding=10)
    frame_config_monitor.pack(fill="both", expand=True, anchor="w")

    def toggle_monitor_topmost():
        monitor_window.attributes('-topmost', monitor_topmost_var.get())
        salvar_configuracoes()

    ttk.Checkbutton(frame_config_monitor, text="Janela no Topo", variable=monitor_topmost_var, command=toggle_monitor_topmost).pack(anchor="w", padx=10, pady=5)

    def toggle_position_right():
        if monitor_position_right_var.get():
            monitor_position_left_var.set(False)
        salvar_configuracoes()

    def toggle_position_left():
        if monitor_position_left_var.get():
            monitor_position_right_var.set(False)
        salvar_configuracoes()

    ttk.Checkbutton(frame_config_monitor, text="Abrir Monitoramento à Direita", variable=monitor_position_right_var, command=toggle_position_right).pack(anchor="w", padx=10, pady=2)
    ttk.Checkbutton(frame_config_monitor, text="Abrir Monitoramento à Esquerda", variable=monitor_position_left_var, command=toggle_position_left).pack(anchor="w", padx=10, pady=2)

    frame_tempo_atualizacao = ttk.Frame(frame_config_monitor)
    frame_tempo_atualizacao.pack(fill="x", padx=10, pady=5)

    label_tempo = ttk.Label(frame_tempo_atualizacao, text="Tempo de Atualização (segundos):")
    label_tempo.pack(side="left", padx=(0, 5))

    entry_monitor_tempo = ttk.Entry(frame_tempo_atualizacao, width=8, textvariable=monitor_tempo_atualizacao_var)
    entry_monitor_tempo.pack(side="left", padx=(0, 10))

    realtime_var = tk.BooleanVar(value=True)
    def toggle_realtime():
        if realtime_var.get():
            monitor_tempo_atualizacao_var.set(0)
            entry_monitor_tempo.config(state="disabled")
        else:
            monitor_tempo_atualizacao_var.set(monitor_tempo_atualizacao_padrao / 1000)
            entry_monitor_tempo.config(state="normal")
        salvar_configuracoes()

    ttk.Checkbutton(frame_tempo_atualizacao, text="Tempo Real (0 ms)", variable=realtime_var, command=toggle_realtime).pack(side="left")

    ttk.Label(frame_config_monitor, text="Configurações de Alerta", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

    spread_atual_alert_minimo_var = tk.DoubleVar(value=spread_atual_alert_minimo_padrao)
    ttk.Label(frame_config_monitor, text="Alerta do Spread Atual do Par (%):").pack(anchor="w", padx=10)
    entry_spread_atual_alert = ttk.Entry(frame_config_monitor, width=8, textvariable=spread_atual_alert_minimo_var)
    entry_spread_atual_alert.pack(anchor="w", padx=10)

    profit_alert_minimo_var = tk.DoubleVar(value=profit_alert_minimo_padrao)
    ttk.Label(frame_config_monitor, text="Alerta do Lucro Total (%):").pack(anchor="w", padx=10)
    entry_profit_alert_minimo = ttk.Entry(frame_config_monitor, width=8, textvariable=profit_alert_minimo_var)
    entry_profit_alert_minimo.pack(anchor="w", padx=10)

    def salvar_configuracoes_monitor():
        global monitor_tempo_atualizacao, profit_alert_minimo_padrao, spread_atual_alert_minimo_padrao
        try:
            monitor_tempo_atualizacao = int(float(monitor_tempo_atualizacao_var.get()) * 1000)
            profit_alert_minimo_padrao = float(profit_alert_minimo_var.get())
            spread_atual_alert_minimo_padrao = float(spread_atual_alert_minimo_var.get())
            salvar_configuracoes()
            monitor_notebook.select(tab_calculadora)
        except ValueError as e:
            print(f"Erro ao salvar configurações da calculadora: {e}")

    ttk.Button(frame_config_monitor, text="Salvar", command=salvar_configuracoes_monitor).pack(anchor="w", padx=10, pady=10)

    spread_alert_triggered = False
    profit_alert_triggered = False
    spread_atual_alert_triggered = False

    def atualizar_monitoramento():
        nonlocal spread_alert_triggered, profit_alert_triggered, spread_atual_alert_triggered
        if not monitor_window.winfo_exists():
            return
        fetch_data_async(lambda spot_data, futuros_data: atualizar_monitoramento_callback(spot_data, futuros_data, spread_alert_triggered, profit_alert_triggered, spread_atual_alert_triggered))

    def atualizar_monitoramento_callback(spot_data, futuros_data, prev_spread_alert, prev_profit_alert, prev_spread_atual_alert):
        nonlocal spread_alert_triggered, profit_alert_triggered, spread_atual_alert_triggered
        current_time = datetime.now()
        if ativo in spot_data and ativo in futuros_data:
            current_spot = spot_data[ativo]["price"]
            current_futuros = futuros_data[ativo]["price"]
            label_current_spot.config(text=f"{current_spot:.6f}")
            label_current_futuros.config(text=f"{current_futuros:.6f}")

            if current_spot > 0:
                spread = ((current_futuros - current_spot) / current_spot) * 100
                label_current_spread.config(text=f"{spread:.2f}%")
                if spread > 0:
                    label_current_spread.config(foreground="#006400")
                else:
                    label_current_spread.config(foreground="#FF0000")

                if ativo not in spread_history:
                    spread_history[ativo] = []
                spread_history[ativo].append((current_time, spread))
                inversoes = calcular_inversoes(ativo, current_time)
                label_inversoes.config(text=str(inversoes))

                if ativo not in top5_contagem:
                    top5_contagem[ativo] = [0, current_time]
                else:
                    last_time = top5_contagem[ativo][1]
                    elapsed = (current_time - last_time).total_seconds()
                    top5_contagem[ativo][0] += elapsed
                    top5_contagem[ativo][1] = current_time
                contagem = top5_contagem[ativo][0]
                label_contagem.config(text=f"{int(contagem)}s")

                if spread_alert_var.get():
                    try:
                        threshold = float(entry_spread_alert.get())
                        if spread >= threshold and not prev_spread_alert:
                            if SOUND_AVAILABLE:
                                try:
                                    sound = pygame.mixer.Sound(EAGAINS_SOUND_PATH)
                                    SPREAD_ATUAL_CHANNEL.play(sound, loops=-1)
                                except Exception as e:
                                    print(f"Erro ao reproduzir som de alerta para spread atual: {e}")
                            spread_alert_triggered = True
                            label_current_spread.config(background="#FFFF99")
                        elif spread < threshold or not spread_alert_var.get():
                            if SOUND_AVAILABLE and SPREAD_ATUAL_CHANNEL.get_busy():
                                SPREAD_ATUAL_CHANNEL.stop()
                            spread_alert_triggered = False
                            label_current_spread.config(background="#FFFFFF")
                    except ValueError:
                        print("Erro na conversão do limite de spread.")
                else:
                    if SOUND_AVAILABLE and SPREAD_ATUAL_CHANNEL.get_busy():
                        SPREAD_ATUAL_CHANNEL.stop()
                    spread_alert_triggered = False
                    label_current_spread.config(background="#FFFFFF")

                try:
                    entry_spot = float(entry_spot_price.get())
                    entry_futuros = float(entry_futuros_price.get())
                    profit_spot = ((current_spot - entry_spot) / entry_spot) * 100 if entry_spot > 0 else 0
                    profit_futuros = ((entry_futuros - current_futuros) / entry_futuros) * 100 if entry_futuros > 0 else 0
                    total_profit = profit_spot + profit_futuros
                    if total_profit < 0:
                        label_profit.config(text=f"-{abs(total_profit):.2f}%", foreground="#FF0000")
                    else:
                        label_profit.config(text=f"{total_profit:.2f}%", foreground="#006400")
                    if profit_alert_var.get():
                        try:
                            threshold = float(entry_profit_alert.get())
                            if total_profit >= threshold and not prev_profit_alert:
                                if SOUND_AVAILABLE:
                                    try:
                                        sound = pygame.mixer.Sound(ALERT_SOUND_PATH)
                                        PROFIT_CHANNEL.play(sound, loops=-1)
                                    except Exception as e:
                                        print(f"Erro ao reproduzir som de alerta para lucro: {e}")
                                profit_alert_triggered = True
                                label_profit.config(background="#FFFF99")
                            elif total_profit < threshold or not profit_alert_var.get():
                                if SOUND_AVAILABLE and PROFIT_CHANNEL.get_busy():
                                    PROFIT_CHANNEL.stop()
                                profit_alert_triggered = False
                                label_profit.config(background="#FFFFFF")
                        except ValueError:
                            print("Erro na conversão do limite de lucro.")
                    else:
                        if SOUND_AVAILABLE and PROFIT_CHANNEL.get_busy():
                            PROFIT_CHANNEL.stop()
                        profit_alert_triggered = False
                        label_profit.config(background="#FFFFFF")
                except:
                    label_profit.config(text="Erro", background="#FFFFFF")

            else:
                label_current_spread.config(text="0.00%", foreground="#FF0000", background="#FFFFFF")

        now = datetime.now()
        now_utc = now - timedelta(hours=3)
        funding_times_utc = [6, 14, 22]
        current_hour_utc = now_utc.hour
        current_day = now_utc.date()

        next_funding_utc = None
        for funding_hour in funding_times_utc:
            if current_hour_utc < funding_hour:
                next_funding_utc = datetime.combine(current_day, datetime.min.time()) + timedelta(hours=funding_hour)
                break
        if next_funding_utc is None:
            next_funding_utc = datetime.combine(current_day + timedelta(days=1), datetime.min.time()) + timedelta(hours=funding_times_utc[0])

        next_funding = next_funding_utc + timedelta(hours=3)
        delta = (next_funding - now).total_seconds()
        if delta >= 0:
            mins, secs = divmod(int(delta), 60)
            hours, mins = divmod(mins, 60)
            label_next_funding.config(text=f"{next_funding.strftime('%H:%M:%S')} ({next_funding.day}/{next_funding.month})")
            label_funding_countdown.config(text=f"{hours:02d}:{mins:02d}:{secs:02d}")
        else:
            label_funding_countdown.config(text="Erro no cálculo")

        update_interval = int(monitor_tempo_atualizacao_var.get() * 1000)
        update_interval = max(1, update_interval)
        monitor_window.after(update_interval, atualizar_monitoramento)

    monitor_window.protocol("WM_DELETE_WINDOW", lambda: [parar_som(), monitor_window.destroy()])
    atualizar_monitoramento()

def abrir_configuracoes_avancadas():
    global advanced_config_window
    if advanced_config_window is not None and advanced_config_window.winfo_exists():
        advanced_config_window.destroy()

    advanced_config_window = tk.Toplevel(root)
    advanced_config_window.title("Configurações Avançadas")
    advanced_config_window.geometry("600x650")
    advanced_config_window.resizable(False, False)

    root_x = root.winfo_x()
    root_y = root.winfo_y()
    root_width = root.winfo_width()
    advanced_width = 600
    if monitor_position_right_var.get():
        advanced_config_window.geometry(f"+{root_x + root_width}+{root_y}")
    elif monitor_position_left_var.get():
        advanced_config_window.geometry(f"+{root_x - advanced_width}+{root_y}")
    else:
        advanced_config_window.geometry(f"+{root_x + root_width}+{root_y}")

    advanced_config_window.attributes('-topmost', advanced_topmost_var.get())

    frame_advanced = ttk.Frame(advanced_config_window, padding=20, style="Modern.TFrame")
    frame_advanced.pack(fill="both", expand=True)

    ttk.Label(frame_advanced, text="Configurações das APIs da MEXC", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=10)

    entry_api_spot_price = ttk.Entry(frame_advanced, width=80, style="Modern.TEntry")
    entry_api_spot_price.insert(0, config_inicial["api_spot_price"])
    entry_api_spot_price.pack(anchor="w", padx=10, pady=2)

    entry_api_spot_volume = ttk.Entry(frame_advanced, width=80, style="Modern.TEntry")
    entry_api_spot_volume.insert(0, config_inicial["api_spot_volume"])
    entry_api_spot_volume.pack(anchor="w", padx=10, pady=2)

    entry_api_futures = ttk.Entry(frame_advanced, width=80, style="Modern.TEntry")
    entry_api_futures.insert(0, config_inicial["api_futures"])
    entry_api_futures.pack(anchor="w", padx=10, pady=2)

    ttk.Label(frame_advanced, text="Configurações dos Links MEXC", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=10)

    entry_spot_base_url = ttk.Entry(frame_advanced, width=80, style="Modern.TEntry")
    entry_spot_base_url.insert(0, config_inicial["spot_base_url"])
    entry_spot_base_url.pack(anchor="w", padx=10, pady=2)

    entry_futuros_base_url = ttk.Entry(frame_advanced, width=80, style="Modern.TEntry")
    entry_futuros_base_url.insert(0, config_inicial["futuros_base_url"])
    entry_futuros_base_url.pack(anchor="w", padx=10, pady=2)

    entry_opportunities_base_url = ttk.Entry(frame_advanced, width=80, style="Modern.TEntry")
    entry_opportunities_base_url.insert(0, config_inicial["opportunities_base_url"])
    entry_opportunities_base_url.pack(anchor="w", padx=10, pady=2)

    ttk.Label(frame_advanced, text="Opções de Janela", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=10)

    frame_options = ttk.Frame(frame_advanced, style="Modern.TFrame")
    frame_options.pack(fill="both", expand=True, pady=5)

    def toggle_position_right():
        if monitor_position_right_var.get():
            monitor_position_left_var.set(False)
        salvar_configuracoes()

    def toggle_position_left():
        if monitor_position_left_var.get():
            monitor_position_right_var.set(False)
        salvar_configuracoes()

    def toggle_advanced_topmost():
        advanced_config_window.attributes('-topmost', advanced_topmost_var.get())
        salvar_configuracoes()

    ttk.Checkbutton(frame_options, text="Abrir Configurações Avançadas à Direita", variable=monitor_position_right_var, command=toggle_position_right, style="Modern.TCheckbutton").pack(anchor="w", padx=10, pady=2)
    ttk.Checkbutton(frame_options, text="Abrir Configurações Avançadas à Esquerda", variable=monitor_position_left_var, command=toggle_position_left, style="Modern.TCheckbutton").pack(anchor="w", padx=10, pady=2)
    ttk.Checkbutton(frame_options, text="Janela no Topo", variable=advanced_topmost_var, command=toggle_advanced_topmost, style="Modern.TCheckbutton").pack(anchor="w", padx=10, pady=2)

    def salvar_configuracoes_avancadas():
        global api_spot_price, api_spot_volume, api_futures, SPOT_BASE_URL, FUTUROS_BASE_URL, opportunities_base_url
        api_spot_price = entry_api_spot_price.get()
        api_spot_volume = entry_api_spot_volume.get()
        api_futures = entry_api_futures.get()
        SPOT_BASE_URL = entry_spot_base_url.get()
        FUTUROS_BASE_URL = entry_futuros_base_url.get()
        opportunities_base_url = entry_opportunities_base_url.get()
        salvar_configuracoes()
        advanced_config_window.destroy()

    ttk.Button(frame_advanced, text="Salvar", command=salvar_configuracoes_avancadas, style="Modern.TButton").pack(anchor="w", padx=10, pady=10)

    advanced_config_window.protocol("WM_DELETE_WINDOW", lambda: advanced_config_window.destroy())

frame_config = ttk.Frame(tab_config, padding=20, style="Modern.TFrame")
frame_config.pack(fill="both", expand=True)

config_notebook = ttk.Notebook(frame_config)
tab_filtros = ttk.Frame(config_notebook)
tab_tempo = ttk.Frame(config_notebook)
tab_opcoes = ttk.Frame(config_notebook)
config_notebook.add(tab_filtros, text="Filtros ⚙")
config_notebook.add(tab_tempo, text="Tempo ⏱")
config_notebook.add(tab_opcoes, text="Opções 🌐")
config_notebook.pack(expand=True, fill="both")

frame_filtros = ttk.LabelFrame(tab_filtros, text="Filtros de Mercado", padding=20, style="Modern.TLabelframe")
frame_filtros.pack(padx=20, pady=20, fill="both", expand=True)

ttk.Label(frame_filtros, text="Intervalo de Spread (%)", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
frame_spread = ttk.Frame(frame_filtros, style="Modern.TFrame")
frame_spread.pack(fill="x", pady=5)
ttk.Label(frame_spread, text="Mínimo:", style="Modern.TLabel").pack(side="left", padx=10)
entry_min_spread = ttk.Entry(frame_spread, width=10, style="Modern.TEntry")
entry_min_spread.pack(side="left", padx=5)
entry_min_spread.insert(0, str(config_inicial["min_spread"]))
ttk.Label(frame_spread, text="Máximo:", style="Modern.TLabel").pack(side="left", padx=10)
entry_max_spread = ttk.Entry(frame_spread, width=10, style="Modern.TEntry")
entry_max_spread.pack(side="left", padx=5)
entry_max_spread.insert(0, str(config_inicial["max_spread"]))

ttk.Label(frame_filtros, text="Intervalo de Volume (M)", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
frame_volume = ttk.Frame(frame_filtros, style="Modern.TFrame")
frame_volume.pack(fill="x", pady=5)
ttk.Label(frame_volume, text="Mínimo:", style="Modern.TLabel").pack(side="left", padx=10)
entry_min_volume = ttk.Entry(frame_volume, width=15, style="Modern.TEntry")
entry_min_volume.pack(side="left", padx=5)
entry_min_volume.insert(0, str(config_inicial["min_volume"]))
ttk.Label(frame_volume, text="Máximo:", style="Modern.TLabel").pack(side="left", padx=10)
entry_max_volume = ttk.Entry(frame_volume, width=15, style="Modern.TEntry")
entry_max_volume.pack(side="left", padx=5)
entry_max_volume.insert(0, str(config_inicial["max_volume"]))

ttk.Label(frame_filtros, text="Intervalo de Contagem Máxima (segundos)", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
frame_count_threshold = ttk.Frame(frame_filtros, style="Modern.TFrame")
frame_count_threshold.pack(fill="x", pady=5)
ttk.Label(frame_count_threshold, text="Mínimo:", style="Modern.TLabel").pack(side="left", padx=10)
entry_min_count_threshold = ttk.Entry(frame_count_threshold, width=10, style="Modern.TEntry")
entry_min_count_threshold.pack(side="left", padx=5)
entry_min_count_threshold.insert(0, str(config_inicial["min_count_threshold"]))
ttk.Label(frame_count_threshold, text="Máximo:", style="Modern.TLabel").pack(side="left", padx=10)
entry_max_count_threshold = ttk.Entry(frame_count_threshold, width=10, style="Modern.TEntry")
entry_max_count_threshold.pack(side="left", padx=5)
entry_max_count_threshold.insert(0, str(config_inicial["max_count_threshold"]))

frame_tempo_config = ttk.LabelFrame(tab_tempo, text="Configurações de Tempo", padding=20, style="Modern.TLabelframe")
frame_tempo_config.pack(padx=20, pady=20, fill="both", expand=True)

ttk.Label(frame_tempo_config, text="Tempo de Atualização (segundos):", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
entry_tempo_atualizacao = ttk.Entry(frame_tempo_config, width=10, style="Modern.TEntry")
entry_tempo_atualizacao.pack(anchor="w", padx=10, pady=5)
entry_tempo_atualizacao.insert(0, str(config_inicial["tempo_atualizacao"]))

ttk.Label(frame_tempo_config, text="Tempo Top 5 (minutos):", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
entry_top5_tempo = ttk.Entry(frame_tempo_config, width=10, style="Modern.TEntry")
entry_top5_tempo.pack(anchor="w", padx=10, pady=5)
entry_top5_tempo.insert(0, str(config_inicial["top5_tempo_minutos"]))

ttk.Label(frame_tempo_config, text="Número de Itens Top 5:", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
entry_top5_itens = ttk.Entry(frame_tempo_config, width=10, style="Modern.TEntry")
entry_top5_itens.pack(anchor="w", padx=10, pady=5)
entry_top5_itens.insert(0, str(config_inicial["top5_num_itens"]))

ttk.Label(frame_tempo_config, text="Janela de Inversões (minutos):", font=("Segoe UI", 12, "bold"), style="Modern.TLabel").pack(anchor="w", pady=(10, 5))
entry_inversion_window = ttk.Entry(frame_tempo_config, width=10, style="Modern.TEntry")
entry_inversion_window.pack(anchor="w", padx=10, pady=5)
entry_inversion_window.insert(0, str(config_inicial["inversion_window_minutes"]))

frame_opcoes = ttk.LabelFrame(tab_opcoes, text="Opções Gerais", padding=20, style="Modern.TLabelframe")
frame_opcoes.pack(padx=20, pady=20, fill="both", expand=True)

ttk.Checkbutton(frame_opcoes, text="Janela no Topo", variable=janela_no_topo_var, style="Modern.TCheckbutton").pack(anchor="w", pady=10)

ttk.Checkbutton(frame_opcoes, text="MEXC Spot / MEXC Futures", variable=mexc_enabled_var, command=lambda: gerenciar_atualizacao(), style="Modern.TCheckbutton").pack(anchor="w", pady=10)

ttk.Button(frame_opcoes, text="Configurações Avançadas", command=abrir_configuracoes_avancadas, style="Modern.TButton").pack(anchor="w", pady=10)

ttk.Button(frame_config, text="Salvar", command=lambda: salvar_configuracoes_simples(), style="Modern.TButton").pack(anchor="w", pady=20)

def salvar_configuracoes_simples():
    global min_spread_padrao, max_spread_padrao, min_volume_padrao, max_volume_padrao, tempo_atualizacao, top5_tempo_minutos, top5_num_itens, top5_tempo_minutos_segundos, top5_start_time, inversion_window_minutes, INVERSION_WINDOW, min_count_threshold, max_count_threshold
    try:
        min_spread_padrao = float(entry_min_spread.get())
        max_spread_padrao = float(entry_max_spread.get())
        min_volume_padrao = float(entry_min_volume.get()) * 1_000_000
        max_volume_padrao = float(entry_max_volume.get()) * 1_000_000
        min_count_threshold = float(entry_min_count_threshold.get())
        max_count_threshold = float(entry_max_count_threshold.get())
        tempo_atualizacao = int(float(entry_tempo_atualizacao.get()) * 1000)
        top5_tempo_minutos = float(entry_top5_tempo.get())
        top5_num_itens = int(entry_top5_itens.get())
        inversion_window_minutes = float(entry_inversion_window.get())
        INVERSION_WINDOW = timedelta(minutes=inversion_window_minutes)
        top5_tempo_minutos_segundos = top5_tempo_minutos * 60
        top5_start_time = datetime.now()
        root.attributes('-topmost', janela_no_topo_var.get())
        frame_top5.config(text=f"Top {top5_num_itens} Spreads mais Elevados")
        tree.heading("Inversões", text=f"Inversões ({int(inversion_window_minutes)}m)")
        top5_tree.heading("Inversões", text=f"Inversões ({int(inversion_window_minutes)}m)")
        salvar_configuracoes()
        notebook.select(tab_scanner)
    except ValueError as e:
        print(f"Erro ao salvar configurações simples: {e}")

def gerenciar_atualizacao():
    global update_id
    if mexc_enabled_var.get():
        if update_id is None:
            atualizar()
    else:
        if update_id is not None:
            root.after_cancel(update_id)
            update_id = None

def atualizar_lista(spot_data, futuros_data):
    global spread_history
    current_time = datetime.now()

    for item in tree.get_children():
        tree.delete(item)

    if not mexc_enabled_var.get():
        tree.insert("", "end", values=("Nenhuma corretora selecionada para análise de dados.", "", "", "", "", "", ""), tags=("mensagem",))
        for item in top5_tree.get_children():
            top5_tree.delete(item)
        top5_tree.insert("", "end", values=("", "", "", "", "", ""))
        return

    if not spot_data or not futuros_data:
        tree.insert("", "end", values=("Erro", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"))
        return

    items = []
    ativos_no_intervalo = set()  # Para rastrear quais ativos estão no intervalo de spread

    for ativo in spot_data:
        if ativo not in futuros_data:
            continue

        spot_price = spot_data[ativo]["price"]
        futuros_price = futuros_data[ativo]["price"]
        volume_spot = spot_data[ativo]["volume"]
        volume_futuros = futuros_data[ativo]["volume"]
        funding_rate = futuros_data[ativo]["funding_rate"]

        if spot_price == 0 or futuros_price == 0:
            continue

        spread = ((futuros_price - spot_price) / spot_price) * 100

        # Adicionar o spread ao histórico independentemente de estar no intervalo
        if ativo not in spread_history:
            spread_history[ativo] = []
        spread_history[ativo].append((current_time, spread))
        # Manter apenas os spreads dentro da janela de inversões
        spread_history[ativo] = [(t, s) for t, s in spread_history[ativo] if current_time - t <= INVERSION_WINDOW]

        # Verificar se o spread está no intervalo definido
        if not (min_spread_padrao <= spread <= max_spread_padrao):
            # Se o ativo não está no intervalo, zerar a contagem
            if ativo in top5_contagem:
                top5_contagem[ativo] = [0, current_time]
            continue

        ativos_no_intervalo.add(ativo)

        inversoes = calcular_inversoes(ativo, current_time)

        items.append({
            "ativo": ativo,
            "spot_price": spot_price,
            "futuros_price": futuros_price,
            "spread": spread,
            "volume_spot": volume_spot,
            "volume_futuros": volume_futuros,
            "inversoes": inversoes,
            "funding_rate": funding_rate
        })

    # Zerar a contagem de ativos que não estão mais no intervalo
    for ativo in list(top5_contagem.keys()):
        if ativo not in ativos_no_intervalo:
            top5_contagem[ativo] = [0, current_time]

    items.sort(key=lambda x: x["spread"], reverse=True)

    for item in items:
        tag = "positivo" if item["spread"] >= 0 else "negativo"
        if item["funding_rate"] < 0:
            tag = "negative_funding"
        volume_display = f"{formatar_volume(item['volume_spot'])} / {formatar_volume(item['volume_futuros'])}"
        tree.insert("", "end", values=(
            item["ativo"],
            f"{item['spot_price']:.6f}",
            f"{item['futuros_price']:.6f}",
            f"{item['spread']:.2f}%",
            volume_display,
            item["inversoes"],
            f"{item['funding_rate']}%"
        ), tags=(tag,))

    atualizar_top5(items, current_time)

def atualizar_top5(items, current_time):
    global top5_contagem, top5_start_time, top5_tempo_minutos_segundos, MAX_COUNT_THRESHOLD

    if top5_start_time is None:
        top5_start_time = datetime.now()

    elapsed_time = (current_time - top5_start_time).total_seconds()
    if elapsed_time >= top5_tempo_minutos_segundos:
        top5_contagem = {ativo: [cont, current_time] for ativo, (cont, last_time) in top5_contagem.items() if (current_time - last_time).total_seconds() <= INVERSION_WINDOW.total_seconds()}
        top5_start_time = current_time

    for item in top5_tree.get_children():
        top5_tree.delete(item)

    if not items:
        top5_tree.insert("", "end", values=("", "", "", "", "", ""))
        return

    # Filtrar ativos com volume dentro do intervalo (corrigido para evitar quebra de linha incorreta)
    filtered_items = [item for item in items if min_volume_padrao <= item["volume_spot"] <= max_volume_padrao and min_volume_padrao <= item["volume_futuros"] <= max_volume_padrao]

    # Ordenar por spread e pegar os top N
    filtered_items.sort(key=lambda x: x["spread"], reverse=True)
    top_items = filtered_items[:top5_num_itens]

    for rank, item in enumerate(top_items, 1):
        ativo = item["ativo"]
        spread = item["spread"]
        inversoes = item["inversoes"]

        # Atualizar contagem
        if ativo not in top5_contagem:
            top5_contagem[ativo] = [0, current_time]
        else:
            last_time = top5_contagem[ativo][1]
            elapsed = (current_time - last_time).total_seconds()
            top5_contagem[ativo][0] += elapsed
            top5_contagem[ativo][0] += elapsed
        top5_contagem[ativo][1] = current_time

        contagem = top5_contagem[ativo][0]
        if contagem > MAX_COUNT_THRESHOLD:
            continue

        tag = "positivo" if spread >= 0 else "negativo"
        top5_tree.insert("", "end", values=(
            rank,
            ativo,
            "MEXC Spot / MEXC Futuros",
            f"{spread:.2f}%",
            f"{int(contagem)}s",
            inversoes
        ), tags=(tag,))

def atualizar():
    global update_id
    fetch_data_async(atualizar_lista)
    update_id = root.after(tempo_atualizacao, atualizar)

# Tocar som de inicialização se disponível
if SOUND_AVAILABLE:
    try:
        startup_sound = pygame.mixer.Sound(STARTUP_SOUND_PATH)
        STARTUP_CHANNEL.play(startup_sound)
    except Exception as e:
        print(f"Erro ao reproduzir som de inicialização: {e}")

# Iniciar atualizações de interface
atualizar_data_hora()
atualizar_contagem_regressiva()
verify_login()
gerenciar_atualizacao()

# Iniciar o loop principal
root.mainloop()
