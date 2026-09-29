"""
Ponto Facial - registro de ponto por reconhecimento facial.

Aceita a webcam do PC ou a câmera do celular (DroidCam, Iriun, IP Webcam).
Configure a câmera em "Configurações" (senha padrão do administrador: 1234).
"""
import json
import os
import sqlite3
import threading
import time
import urllib.request
from datetime import date, datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import winsound
except ImportError:  # fora do Windows
    winsound = None

BASE = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BASE) == "__pycache__":  # aberto pelo .pyc por engano
    BASE = os.path.dirname(BASE)
PASTA_DADOS = os.path.join(BASE, "dados")
PASTA_MODELOS = os.path.join(BASE, "modelos")
ARQ_CONFIG = os.path.join(BASE, "config.json")
ARQ_DB = os.path.join(PASTA_DADOS, "ponto.db")

# Modelos oficiais do OpenCV (baixados automaticamente na primeira execução)
MODELOS = {
    "face_detection_yunet_2023mar.onnx": "face_detection_yunet",
    "face_recognition_sface_2021dec.onnx": "face_recognition_sface",
}

CONFIG_PADRAO = {
    "camera": "0",           # 0 = webcam do PC | 1, 2... = outra câmera (DroidCam/Iriun) | http://IP:PORTA/video
    "espelhar": True,        # espelha a imagem (mais natural para quem está na frente)
    "prova_de_vida": True,   # pede para virar o rosto (dificulta fraude com foto)
    "limiar": 0.40,          # semelhança mínima para reconhecer (0 a 1; maior = mais rigoroso)
    "intervalo_min": 5,      # minutos mínimos entre duas batidas da mesma pessoa
    "senha_admin": "1234",
}

TIPOS = ["Entrada", "Saída almoço", "Volta almoço", "Saída"]

# --------------------------------------------------------------------------- #
# Tema visual
# --------------------------------------------------------------------------- #
C = {
    "fundo": "#0a0e1c",
    "lateral": "#0c1224",
    "cartao": "#111831",
    "cartao2": "#0d1428",
    "interno": "#080c18",
    "borda": "#1e2848",
    "hover": "#19213d",
    "texto": "#eef1fb",
    "suave": "#8e98b8",
    "icone": "#c9cfe6",
    "primaria": "#5b5cf0",
    "primaria2": "#4a47d9",
    "primaria_clara": "#8f93ff",
    "destaque": "#1c2450",
    "verde": "#22c55e",
    "vermelho": "#f87171",
}

# Degradês dos cartões (cor da esquerda, cor da direita) e cor do círculo do ícone
GRADIENTE_RELOGIO = ("#111831", "#3b3fbf")
STATUS = {
    "neutro": (("#131b36", "#2a3470"), "#5b5cf0", "pessoa"),
    "info": (("#16307f", "#3657d6"), "#5b7cf5", "info"),
    "ok": (("#0f5c34", "#1f9d55"), "#34d27a", "ok"),
    "aviso": (("#6e4b05", "#b98309"), "#e3a51c", "aviso"),
    "erro": (("#8f1830", "#d23a52"), "#f0506a", "erro"),
}

# Ícones da fonte Segoe (já vem no Windows 10/11)
ARQ_FONTE_ICONES = next(
    (p for p in (r"C:\Windows\Fonts\SegoeIcons.ttf", r"C:\Windows\Fonts\segmdl2.ttf") if os.path.exists(p)), None
)
FONTE_ICONES = "Segoe Fluent Icons" if ARQ_FONTE_ICONES and ARQ_FONTE_ICONES.endswith("SegoeIcons.ttf") else "Segoe MDL2 Assets"
IC = {
    "inicio": "\uE80F", "pessoa": "\uE77B", "pessoas": "\uE716", "add_pessoa": "\uE8FA",
    "doc": "\uE8A5", "config": "\uE713", "relogio": "\uE823", "calendario": "\uE787",
    "camera": "\uE722", "erro": "\uE783", "aviso": "\uE7BA", "ok": "\uE73E", "info": "\uE946",
    "cadeado": "\uE72E", "salvar": "\uE74E", "lixeira": "\uE74D",
}

ESCALA = 1.0  # escala da tela (125%, 150%...), calculada ao abrir


def px(valor):
    return int(round(valor * ESCALA))


def fonte(tam, peso="normal"):
    return ctk.CTkFont(family="Segoe UI", size=tam, weight=peso)


_icones = {}


def icone(nome, cor, tam=20):
    chave = (nome, cor, tam)
    if chave not in _icones:
        if not ARQ_FONTE_ICONES:
            return None
        lado = tam * 3
        img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        glifos = ImageFont.truetype(ARQ_FONTE_ICONES, int(lado * 0.8))
        ImageDraw.Draw(img).text((lado / 2, lado / 2), IC[nome], font=glifos, fill=cor, anchor="mm")
        _icones[chave] = ctk.CTkImage(light_image=img, dark_image=img, size=(tam, tam))
    return _icones[chave]


def cartao(master, **kw):
    return ctk.CTkFrame(master, fg_color=C["cartao"], corner_radius=16, border_width=1, border_color=C["borda"], **kw)


def botao(master, texto, comando, tipo="primario", nome_icone=None, **kw):
    fg, hover, cor_texto, borda = {
        "primario": (C["primaria"], C["primaria2"], "#ffffff", 0),
        "sucesso": ("#16a34a", "#15803d", "#ffffff", 0),
        "perigo": ("#b91c1c", "#991b1b", "#ffffff", 0),
        "secundario": (C["cartao"], C["hover"], C["texto"], 1),
    }[tipo]
    return ctk.CTkButton(
        master, text=texto, command=comando, fg_color=fg, hover_color=hover, text_color=cor_texto,
        border_width=borda, border_color=C["borda"], corner_radius=10, height=40, font=fonte(14),
        image=icone(nome_icone, "#ffffff" if borda == 0 else C["icone"], 18) if nome_icone else None, **kw,
    )


def campo(master, rotulo, var, largura=300, **kw):
    ctk.CTkLabel(master, text=rotulo, font=fonte(13), text_color=C["suave"]).pack(anchor="w", padx=20)
    entrada = ctk.CTkEntry(
        master, textvariable=var, width=largura, height=38, fg_color=C["interno"],
        border_color=C["borda"], text_color=C["texto"], font=fonte(14), **kw,
    )
    entrada.pack(anchor="w", padx=20, pady=(2, 10))
    return entrada


def estilo_tabela(root):
    estilo = ttk.Style(root)
    estilo.theme_use("clam")
    estilo.configure(
        "Escuro.Treeview", background=C["cartao2"], fieldbackground=C["cartao2"], foreground=C["texto"],
        rowheight=px(34), borderwidth=0, font=("Segoe UI", 11),
    )
    estilo.map("Escuro.Treeview", background=[("selected", "#2a2f7a")], foreground=[("selected", "#ffffff")])
    estilo.configure(
        "Escuro.Treeview.Heading", background="#161f3b", foreground=C["texto"], relief="flat",
        borderwidth=0, font=("Segoe UI", 11, "bold"), padding=(px(10), px(8)),
    )
    estilo.map("Escuro.Treeview.Heading", background=[("active", "#1c2648")])
    estilo.layout("Escuro.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])


def tabela(master, colunas, altura=10):
    """Treeview escura com barra de rolagem. colunas = [(id, título, largura, alinhamento)]."""
    caixa = ctk.CTkFrame(master, fg_color=C["cartao2"], corner_radius=12)
    arvore = ttk.Treeview(caixa, style="Escuro.Treeview", columns=[c[0] for c in colunas], show="headings", height=altura)
    for col, titulo, largura, alinhar in colunas:
        arvore.heading(col, text=titulo, anchor=alinhar)
        arvore.column(col, width=px(largura), anchor=alinhar)
    rolagem = ctk.CTkScrollbar(caixa, command=arvore.yview, button_color=C["borda"], button_hover_color=C["primaria"])
    arvore.configure(yscrollcommand=rolagem.set)
    rolagem.pack(side="right", fill="y", padx=(0, 4), pady=8)
    arvore.pack(side="left", fill="both", expand=True, padx=px(6), pady=px(6))
    return caixa, arvore


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
def carregar_config():
    cfg = dict(CONFIG_PADRAO)
    try:
        with open(ARQ_CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        salvar_config(cfg)
    except (json.JSONDecodeError, OSError):
        pass
    return cfg


def salvar_config(cfg):
    with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Banco de dados
# --------------------------------------------------------------------------- #
class Banco:
    def __init__(self, caminho):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        self.con = sqlite3.connect(caminho)
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS funcionarios (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula  TEXT NOT NULL UNIQUE,
                nome       TEXT NOT NULL,
                cpf        TEXT,
                biometria  BLOB,
                ativo      INTEGER NOT NULL DEFAULT 1,
                criado_em  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS registros (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                funcionario_id INTEGER NOT NULL REFERENCES funcionarios(id),
                data_hora      TEXT NOT NULL,
                tipo           TEXT NOT NULL,
                similaridade   REAL
            );
            CREATE INDEX IF NOT EXISTS idx_registros_data ON registros(data_hora);
            """
        )
        self.carregar_biometrias()

    def carregar_biometrias(self):
        linhas = self.con.execute(
            "SELECT id, nome, biometria FROM funcionarios WHERE ativo = 1 AND biometria IS NOT NULL"
        ).fetchall()
        self.ids = [l[0] for l in linhas]
        self.nomes = {l[0]: l[1] for l in linhas}
        if linhas:
            self.matriz = np.stack([np.frombuffer(l[2], dtype=np.float32) for l in linhas])
        else:
            self.matriz = np.zeros((0, 128), dtype=np.float32)

    def identificar(self, emb):
        """Retorna (id do funcionário mais parecido, semelhança)."""
        if not self.ids:
            return None, 0.0
        semelhancas = self.matriz @ emb
        i = int(np.argmax(semelhancas))
        return self.ids[i], float(semelhancas[i])

    def cadastrar(self, matricula, nome, cpf, emb):
        self.con.execute(
            "INSERT INTO funcionarios (matricula, nome, cpf, biometria, criado_em) VALUES (?, ?, ?, ?, ?)",
            (matricula, nome, cpf, emb.astype(np.float32).tobytes(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        self.con.commit()
        self.carregar_biometrias()

    def listar_funcionarios(self):
        return self.con.execute(
            "SELECT id, matricula, nome, cpf, criado_em, ativo FROM funcionarios ORDER BY ativo DESC, nome"
        ).fetchall()

    def desativar(self, fid):
        """Desliga o funcionário e apaga a biometria (LGPD). As batidas antigas são mantidas."""
        self.con.execute("UPDATE funcionarios SET ativo = 0, biometria = NULL WHERE id = ?", (fid,))
        self.con.commit()
        self.carregar_biometrias()

    def ultima_batida(self, fid):
        linha = self.con.execute(
            "SELECT data_hora FROM registros WHERE funcionario_id = ? ORDER BY data_hora DESC LIMIT 1", (fid,)
        ).fetchone()
        return datetime.strptime(linha[0], "%Y-%m-%d %H:%M:%S") if linha else None

    def registrar(self, fid, similaridade):
        agora = datetime.now()
        n = self.con.execute(
            "SELECT COUNT(*) FROM registros WHERE funcionario_id = ? AND data_hora LIKE ?",
            (fid, agora.strftime("%Y-%m-%d") + "%"),
        ).fetchone()[0]
        tipo = TIPOS[n] if n < len(TIPOS) else "Extra"
        self.con.execute(
            "INSERT INTO registros (funcionario_id, data_hora, tipo, similaridade) VALUES (?, ?, ?, ?)",
            (fid, agora.strftime("%Y-%m-%d %H:%M:%S"), tipo, round(similaridade, 3)),
        )
        self.con.commit()
        return tipo, agora

    def registros_do_dia(self, dia):
        return self.con.execute(
            """SELECT substr(r.data_hora, 12, 5), f.nome, r.tipo
               FROM registros r JOIN funcionarios f ON f.id = r.funcionario_id
               WHERE r.data_hora LIKE ? ORDER BY r.data_hora DESC""",
            (dia.strftime("%Y-%m-%d") + "%",),
        ).fetchall()

    def registros_periodo(self, inicio, fim):
        return self.con.execute(
            """SELECT f.matricula, f.nome, r.data_hora, r.tipo
               FROM registros r JOIN funcionarios f ON f.id = r.funcionario_id
               WHERE r.data_hora BETWEEN ? AND ? ORDER BY f.nome, r.data_hora""",
            (inicio.strftime("%Y-%m-%d") + " 00:00:00", fim.strftime("%Y-%m-%d") + " 23:59:59"),
        ).fetchall()


# --------------------------------------------------------------------------- #
# Câmera (webcam ou celular) lida em segundo plano
# --------------------------------------------------------------------------- #
def redimensionar(frame, largura=640):
    h, w = frame.shape[:2]
    if w <= largura:
        return frame
    escala = largura / w
    return cv2.resize(frame, (largura, int(h * escala)), interpolation=cv2.INTER_AREA)


class Camera:
    def __init__(self, fonte_camera, espelhar=True):
        self.fonte = str(fonte_camera).strip()
        self.espelhar = espelhar
        self.frame = None
        self.ultimo = 0.0
        self.estado = "conectando"  # conectando | ativa | erro
        self.erro = ("Conectando à câmera...", "Aguarde alguns segundos.")
        self.lock = threading.Lock()
        self.rodando = False

    def _abrir(self):
        if self.fonte.isdigit():
            # Media Foundation funciona com o DroidCam novo; DirectShow fica de reserva
            for api in (cv2.CAP_MSMF, cv2.CAP_DSHOW):
                cap = cv2.VideoCapture(int(self.fonte), api)
                if cap.isOpened():
                    return cap
                cap.release()
            return cap
        # Câmera do celular pela rede (DroidCam / IP Webcam)
        return cv2.VideoCapture(self.fonte, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000])

    def iniciar(self):
        self.rodando = True
        threading.Thread(target=self._loop, daemon=True).start()

    def parar(self):
        self.rodando = False

    def _loop(self):
        cap, falhas = None, 0
        while self.rodando:
            if cap is None:
                cap = self._abrir()
                if not cap.isOpened():
                    cap.release()
                    cap = None
                    self.estado = "erro"
                    self.erro = (
                        f"Não foi possível abrir a câmera \"{self.fonte}\".",
                        "Verifique se o celular e o PC estão na mesma rede e se o app da câmera está aberto.",
                    )
                    time.sleep(2)
                    continue
                self.erro = None
            ok, frame = cap.read()
            if not ok or frame is None:
                falhas += 1
                time.sleep(0.05)
                if falhas > 40:
                    cap.release()
                    cap, falhas = None, 0
                    self.estado = "erro"
                    self.erro = ("Sinal da câmera perdido.", "Tentando reconectar automaticamente...")
                continue
            falhas = 0
            frame = redimensionar(frame)
            if self.espelhar:
                frame = cv2.flip(frame, 1)
            with self.lock:
                self.frame = frame
                self.ultimo = time.time()
                self.estado = "ativa"
        if cap is not None:
            cap.release()

    def ler(self):
        with self.lock:
            if self.frame is None or time.time() - self.ultimo > 3:
                return None
            return self.frame.copy()


# --------------------------------------------------------------------------- #
# Reconhecimento facial (YuNet + SFace do OpenCV)
# --------------------------------------------------------------------------- #
def caminho_modelo(nome):
    return os.path.join(PASTA_MODELOS, nome)


def modelo_ok(nome):
    p = caminho_modelo(nome)
    return os.path.exists(p) and os.path.getsize(p) > 100_000


def baixar_modelos(root):
    faltando = [n for n in MODELOS if not modelo_ok(n)]
    if not faltando:
        return
    os.makedirs(PASTA_MODELOS, exist_ok=True)
    janela = ctk.CTkToplevel(root, fg_color=C["fundo"])
    janela.title("Ponto Facial")
    rotulo = ctk.CTkLabel(janela, text="Primeira execução: baixando modelos de reconhecimento facial...",
                          font=fonte(14), text_color=C["texto"])
    rotulo.pack(padx=30, pady=(24, 10))
    barra = ctk.CTkProgressBar(janela, width=380, progress_color=C["primaria"], fg_color=C["interno"])
    barra.set(0)
    barra.pack(padx=30, pady=(0, 24))
    janela.update()

    for nome in faltando:
        pasta = MODELOS[nome]
        urls = [
            f"https://github.com/opencv/opencv_zoo/raw/main/models/{pasta}/{nome}",
            f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{pasta}/{nome}",
        ]
        temp = caminho_modelo(nome) + ".part"
        erro = None

        def progresso(blocos, tam_bloco, total, nome=nome):
            if total > 0:
                fracao = min(1.0, blocos * tam_bloco / total)
                rotulo.configure(text=f"Baixando {nome}... {int(fracao * 100)}%")
                barra.set(fracao)
                janela.update()

        for url in urls:
            try:
                urllib.request.urlretrieve(url, temp, reporthook=progresso)
                if os.path.getsize(temp) > 100_000:
                    os.replace(temp, caminho_modelo(nome))
                    break
            except Exception as e:  # tenta o próximo endereço
                erro = e
        else:
            janela.destroy()
            raise RuntimeError(f"Não foi possível baixar o modelo {nome}.\nVerifique a internet.\n\n{erro}")
    janela.destroy()


class Rosto:
    def __init__(self):
        self.detector = cv2.FaceDetectorYN.create(
            caminho_modelo("face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.85, 0.3, 5000
        )
        self.reconhecedor = cv2.FaceRecognizerSF.create(caminho_modelo("face_recognition_sface_2021dec.onnx"), "")

    def detectar(self, frame):
        """Rostos encontrados, do maior (mais próximo) para o menor."""
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []
        return sorted(faces, key=lambda f: f[2] * f[3], reverse=True)

    def embedding(self, frame, face):
        alinhado = self.reconhecedor.alignCrop(frame, face)
        vetor = self.reconhecedor.feature(alinhado).flatten().astype(np.float32)
        return vetor / np.linalg.norm(vetor)

    @staticmethod
    def giro(face):
        """Quanto o rosto está virado para o lado (0 = de frente)."""
        olho_d, olho_e, nariz = face[4:6], face[6:8], face[8:10]
        dist_olhos = max(abs(olho_e[0] - olho_d[0]), 1.0)
        return (nariz[0] - (olho_d[0] + olho_e[0]) / 2) / dist_olhos


def desenhar_rosto(img, face, cor):
    x, y, w, h = [int(v) for v in face[:4]]
    cv2.rectangle(img, (x, y), (x + w, y + h), cor, 2)
    for i in range(4, 14, 2):
        cv2.circle(img, (int(face[i]), int(face[i + 1])), 2, cor, -1)


def bip(sucesso=True):
    if winsound:
        winsound.MessageBeep(winsound.MB_OK if sucesso else winsound.MB_ICONHAND)


# --------------------------------------------------------------------------- #
# Desenhos (imagens para a tela)
# --------------------------------------------------------------------------- #
def rgb(cor):
    cor = cor.lstrip("#")
    return np.array([int(cor[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def foto_rgb(img):
    h, w = img.shape[:2]
    return tk.PhotoImage(data=f"P6 {w} {h} 255 ".encode() + np.ascontiguousarray(img).tobytes(), format="PPM")


def foto_bgr(frame):
    return foto_rgb(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def foto_cartao(w, h, cor1, cor2, cor_fundo, raio):
    """Cartão com cantos arredondados e degradê diagonal."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    t = np.clip(x / max(w - 1, 1) * 0.75 + (1 - y / max(h - 1, 1)) * 0.25, 0, 1) ** 1.8
    a, b = rgb(cor1), rgb(cor2)
    img = a + (b - a) * t[..., None]
    meio_w, meio_h = (w - 1) / 2, (h - 1) / 2
    qx = np.abs(x - meio_w) - (meio_w - raio)
    qy = np.abs(y - meio_h) - (meio_h - raio)
    dist = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - raio
    borda = (np.clip(1 - np.abs(dist + 1.0), 0, 1) * 0.15)[..., None]
    img = img * (1 - borda) + 255 * borda
    alfa = np.clip(0.5 - dist, 0, 1)[..., None]
    img = rgb(cor_fundo) * (1 - alfa) + img * alfa
    return foto_rgb(img.astype(np.uint8))


def desenhar_logo(cv, cx, cy, s, cor, tag, espessura):
    """Ícone de reconhecimento facial: cantos de mira + pessoa."""
    meio, perna = s / 2, s * 0.28
    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        x, y = cx + dx * meio, cy + dy * meio
        cv.create_line(x, y - dy * perna, x, y, x - dx * perna, y, fill=cor, width=espessura,
                       capstyle="round", joinstyle="round", tags=tag)
    r = s * 0.13
    cv.create_oval(cx - r, cy - s * 0.2 - r, cx + r, cy - s * 0.2 + r, outline=cor, width=espessura, tags=tag)
    cv.create_arc(cx - s * 0.26, cy + s * 0.02, cx + s * 0.26, cy + s * 0.5, start=0, extent=180,
                  style="arc", outline=cor, width=espessura, tags=tag)


class PainelVideo(tk.Canvas):
    """Área da câmera com cantos de mira e aviso quando não há imagem."""

    def __init__(self, master, **kw):
        super().__init__(master, bg=C["interno"], highlightthickness=0, bd=0, **kw)
        self.img_id = self.create_image(0, 0)
        self._foto = None
        self._modo = None
        self.bind("<Configure>", lambda e: self._moldura())

    def _moldura(self):
        self.delete("moldura")
        w, h = self.winfo_width(), self.winfo_height()
        m, perna = px(16), px(26)
        for x, y, dx, dy in [(m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)]:
            self.create_line(x, y + dy * perna, x, y, x + dx * perna, y, fill=C["primaria"], width=px(3),
                             capstyle="round", joinstyle="round", tags="moldura")
        self._modo = None  # redesenha o aviso no novo tamanho

    def mostrar(self, frame):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        if frame is None:
            if self._modo != "vazio":
                self._modo = "vazio"
                self._foto = None
                self.itemconfig(self.img_id, image="")
                self.delete("vazio")
                cx, cy = w / 2, h / 2
                desenhar_logo(self, cx, cy - px(70), px(84), C["primaria"], "vazio", px(4))
                self.create_text(cx, cy + px(12), text="Sem imagem da câmera", fill=C["texto"],
                                 font=("Segoe UI", 18, "bold"), tags="vazio")
                self.create_text(cx, cy + px(58), fill=C["suave"], font=("Segoe UI", 12), justify="center",
                                 text="Verifique se a câmera está conectada\ne se o app tem permissão para acessá-la.",
                                 tags="vazio")
            return
        if self._modo != "video":
            self._modo = "video"
            self.delete("vazio")
        fh, fw = frame.shape[:2]
        esc = min(w / fw, h / fh)
        img = cv2.resize(frame, (max(1, int(fw * esc)), max(1, int(fh * esc))), interpolation=cv2.INTER_LINEAR)
        self._foto = foto_bgr(img)
        self.itemconfig(self.img_id, image=self._foto)
        self.coords(self.img_id, w / 2, h / 2)
        self.tag_raise("moldura")


class CartaoDegrade(tk.Canvas):
    """Cartão com degradê desenhado em um Canvas (o CustomTkinter não faz degradê)."""

    def __init__(self, master, cores, cor_fundo, altura, raio=18):
        super().__init__(master, height=px(altura), bg=cor_fundo, highlightthickness=0, bd=0)
        self.cores, self.cor_fundo, self.raio = cores, cor_fundo, px(raio)
        self._foto = None
        self._tam = (0, 0)
        self.fundo_id = self.create_image(0, 0, anchor="nw")
        self.bind("<Configure>", self._redimensionar)

    def definir_cores(self, cores):
        if cores != self.cores:
            self.cores = cores
            self._pintar()

    def _redimensionar(self, evento):
        if (evento.width, evento.height) != self._tam:
            self._tam = (evento.width, evento.height)
            self._pintar()
            self.posicionar()

    def _pintar(self):
        w, h = self._tam
        if w < 4 or h < 4:
            return
        self._foto = foto_cartao(w, h, *self.cores, self.cor_fundo, self.raio)
        self.itemconfig(self.fundo_id, image=self._foto)
        self.tag_lower(self.fundo_id)

    def posicionar(self):
        pass


class CartaoRelogio(CartaoDegrade):
    def __init__(self, master, cor_fundo):
        super().__init__(master, GRADIENTE_RELOGIO, cor_fundo, 170)
        self.circulo = self.create_oval(0, 0, 0, 0, fill=C["primaria"], outline="")
        self.ic = self.create_text(0, 0, text=IC["relogio"], font=(FONTE_ICONES, 26), fill="#ffffff")
        self.hora = self.create_text(0, 0, anchor="w", font=("Segoe UI", 44, "bold"), fill="#ffffff")
        self.ic_cal = self.create_text(0, 0, anchor="w", text=IC["calendario"], font=(FONTE_ICONES, 15),
                                       fill=C["primaria_clara"])
        self.data = self.create_text(0, 0, anchor="w", font=("Segoe UI", 15), fill="#c9cfe6")

    def posicionar(self):
        h = self._tam[1]
        r = px(36)
        cx, cy = px(28) + r, h / 2
        self.coords(self.circulo, cx - r, cy - r, cx + r, cy + r)
        self.coords(self.ic, cx, cy)
        x = cx + r + px(32)
        self.coords(self.hora, x, cy - px(14))
        self.coords(self.ic_cal, x, cy + px(42))
        self.coords(self.data, x + px(30), cy + px(42))

    def atualizar(self, hora, data):
        self.itemconfig(self.hora, text=hora)
        self.itemconfig(self.data, text=data)


class CartaoStatus(CartaoDegrade):
    def __init__(self, master, cor_fundo):
        super().__init__(master, STATUS["neutro"][0], cor_fundo, 150)
        self.circulo = self.create_oval(0, 0, 0, 0, fill=STATUS["neutro"][1], outline="")
        self.ic = self.create_text(0, 0, font=(FONTE_ICONES, 24), fill="#ffffff")
        self.titulo = self.create_text(0, 0, anchor="nw", font=("Segoe UI", 15, "bold"), fill="#ffffff")
        self.corpo = self.create_text(0, 0, anchor="nw", font=("Segoe UI", 12), fill="#f1f3fb")

    def definir(self, tipo, titulo, corpo=""):
        cores, cor_circulo, nome_icone = STATUS[tipo]
        self.definir_cores(cores)
        self.itemconfig(self.circulo, fill=cor_circulo)
        self.itemconfig(self.ic, text=IC[nome_icone])
        self.itemconfig(self.titulo, text=titulo)
        self.itemconfig(self.corpo, text=corpo)
        self.posicionar()

    def posicionar(self):
        w, h = self._tam
        if w < 4:
            return
        r = px(34)
        cx, cy = px(28) + r, h / 2
        self.coords(self.circulo, cx - r, cy - r, cx + r, cy + r)
        self.coords(self.ic, cx, cy)
        x = cx + r + px(26)
        largura = max(w - x - px(24), 50)
        self.itemconfig(self.titulo, width=largura)
        self.itemconfig(self.corpo, width=largura)
        self.coords(self.titulo, x, 0)
        self.coords(self.corpo, x, 0)
        bt, bc = self.bbox(self.titulo), self.bbox(self.corpo)
        alt_t = bt[3] - bt[1] if bt else 0
        alt_c = bc[3] - bc[1] if bc and self.itemcget(self.corpo, "text") else 0
        espaco = px(6) if alt_c else 0
        y0 = (h - alt_t - espaco - alt_c) / 2
        self.coords(self.titulo, x, y0)
        self.coords(self.corpo, x, y0 + alt_t + espaco)


# --------------------------------------------------------------------------- #
# Tela principal
# --------------------------------------------------------------------------- #
BADGES = {
    "ativa": ("●  Câmera ativa", "#0f2e22", "#4ade80"),
    "conectando": ("●  Conectando...", "#33280a", "#fbbf24"),
    "erro": ("●  Câmera desconectada", "#3a1119", "#f87171"),
}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


class App:
    def __init__(self, root, cfg, banco, rosto):
        self.root, self.cfg, self.banco, self.rosto = root, cfg, banco, rosto
        self.estado = "aguardando"
        self.candidato = None
        self.conta = 0
        self.desconhecido = 0
        self.desafio_inicio = 0.0
        self.virou = False
        self.msg_ate = 0.0
        self.status_atual = None
        self.badge_atual = None
        self.erro_camera_visivel = False
        self.pausado = False
        self.admin_ate = 0.0
        self.frame_atual = None

        estilo_tabela(root)
        self._montar_tela()
        self.camera = Camera(cfg["camera"], cfg["espelhar"])
        self.camera.iniciar()
        root.protocol("WM_DELETE_WINDOW", self.sair)
        self.status_padrao()
        self.atualizar_lista()
        self.atualizar_relogio()
        self.loop()

    # ---------- interface ----------
    def _montar_tela(self):
        r = self.root
        r.title("Ponto Facial")
        r.configure(fg_color=C["fundo"])
        r.minsize(1100, 680)
        r.grid_columnconfigure(1, weight=1)
        r.grid_rowconfigure(2, weight=1)

        # Cabeçalho
        topo = ctk.CTkFrame(r, fg_color=C["fundo"], corner_radius=0)
        topo.grid(row=0, column=0, columnspan=2, sticky="ew")
        logo = tk.Canvas(topo, width=px(58), height=px(58), bg=C["fundo"], highlightthickness=0)
        logo.pack(side="left", padx=(px(28), px(16)), pady=px(16))
        desenhar_logo(logo, px(29), px(29), px(48), C["primaria"], "logo", px(3))

        marca = ctk.CTkFrame(topo, fg_color="transparent")
        marca.pack(side="left")
        linha = ctk.CTkFrame(marca, fg_color="transparent")
        linha.pack(anchor="w")
        ctk.CTkLabel(linha, text="Ponto", font=fonte(26, "bold"), text_color=C["texto"], height=34).pack(side="left")
        ctk.CTkLabel(linha, text=" Facial", font=fonte(26, "bold"), text_color=C["primaria_clara"], height=34).pack(side="left")
        ctk.CTkLabel(marca, text="Controle de acesso e frequência", font=fonte(13), text_color=C["suave"],
                     height=18).pack(anchor="w")

        botoes_topo = [
            ("Configurações", "config", C["icone"], self.abrir_config),
            ("Relatório Excel", "doc", C["verde"], self.abrir_relatorio),
            ("Funcionários", "pessoas", C["icone"], self.abrir_funcionarios),
            ("Cadastrar funcionário", "add_pessoa", C["primaria_clara"], self.abrir_cadastro),
        ]
        for i, (texto, nome_icone, cor, acao) in enumerate(botoes_topo):
            ctk.CTkButton(
                topo, text=texto, image=icone(nome_icone, cor, 20), compound="left", height=44, corner_radius=10,
                fg_color=C["cartao"], hover_color=C["hover"], border_width=1, border_color=C["borda"],
                text_color=C["texto"], font=fonte(14), command=acao,
            ).pack(side="right", padx=(0, 24 if i == 0 else 12))

        ctk.CTkFrame(r, height=1, fg_color=C["borda"], corner_radius=0).grid(row=1, column=0, columnspan=2, sticky="ew")

        # Menu lateral
        lateral = ctk.CTkFrame(r, fg_color=C["lateral"], corner_radius=0, width=230)
        lateral.grid(row=2, column=0, sticky="ns")
        lateral.pack_propagate(False)
        menu = [
            ("Início", "inicio", None),
            ("Funcionários", "pessoa", self.abrir_funcionarios),
            ("Relatórios", "doc", self.abrir_relatorio),
            ("Configurações", "config", self.abrir_config),
        ]
        for i, (texto, nome_icone, acao) in enumerate(menu):
            ativo = acao is None
            ctk.CTkButton(
                lateral, text="  " + texto, image=icone(nome_icone, "#ffffff" if ativo else C["icone"], 22),
                anchor="w", height=52, corner_radius=10, font=fonte(15), text_color=C["texto"],
                fg_color=C["primaria2"] if ativo else "transparent",
                hover_color=C["primaria2"] if ativo else C["hover"],
                command=acao or (lambda: None),
            ).pack(fill="x", padx=16, pady=(22 if i == 0 else 8, 0))

        rodape = ctk.CTkFrame(lateral, fg_color="transparent")
        rodape.pack(side="bottom", fill="x", padx=24, pady=24)
        ctk.CTkLabel(rodape, text="●", text_color=C["verde"], font=fonte(16), height=20).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(rodape, text="Sistema Online", font=fonte(14), text_color=C["texto"], height=20).grid(
            row=0, column=1, sticky="w")
        ctk.CTkLabel(rodape, text="Pronto para uso", font=fonte(12), text_color=C["suave"], height=18).grid(
            row=1, column=1, sticky="w")

        # Conteúdo
        conteudo = ctk.CTkFrame(r, fg_color=C["fundo"], corner_radius=0)
        conteudo.grid(row=2, column=1, sticky="nsew")
        conteudo.grid_columnconfigure(0, weight=3)
        conteudo.grid_columnconfigure(1, weight=2)
        conteudo.grid_rowconfigure(0, weight=1)

        # Cartão da câmera
        cam = cartao(conteudo)
        cam.grid(row=0, column=0, sticky="nsew", padx=(24, 12), pady=24)
        cab = ctk.CTkFrame(cam, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(18, 12))
        ctk.CTkLabel(cab, text="", image=icone("camera", C["primaria_clara"], 24), width=48, height=48,
                     fg_color=C["destaque"], corner_radius=12).pack(side="left")
        textos = ctk.CTkFrame(cab, fg_color="transparent")
        textos.pack(side="left", padx=14)
        ctk.CTkLabel(textos, text="Ponto Facial", font=fonte(20, "bold"), text_color=C["texto"], height=26).pack(anchor="w")
        ctk.CTkLabel(textos, text="Posicione o rosto na frente da câmera", font=fonte(13), text_color=C["suave"],
                     height=18).pack(anchor="w")
        self.badge = ctk.CTkLabel(cab, text="", font=fonte(13), corner_radius=14, height=34)
        self.badge.pack(side="right")

        caixa = ctk.CTkFrame(cam, fg_color=C["interno"], corner_radius=14, border_width=1, border_color=C["borda"])
        caixa.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.video = PainelVideo(caixa)
        self.video.pack(fill="both", expand=True, padx=px(8), pady=px(8))

        # Coluna da direita
        direita = ctk.CTkFrame(conteudo, fg_color="transparent")
        direita.grid(row=0, column=1, sticky="nsew", padx=(12, 24), pady=24)
        self.relogio = CartaoRelogio(direita, C["fundo"])
        self.relogio.pack(fill="x")
        self.cartao_status = CartaoStatus(direita, C["fundo"])
        self.cartao_status.pack(fill="x", pady=px(22))

        batidas = cartao(direita)
        batidas.pack(fill="both", expand=True)
        cab2 = ctk.CTkFrame(batidas, fg_color="transparent")
        cab2.pack(fill="x", padx=20, pady=(16, 12))
        ctk.CTkLabel(cab2, text="", image=icone("calendario", C["primaria_clara"], 26), width=30).pack(side="left")
        ctk.CTkLabel(cab2, text="Batidas de hoje", font=fonte(18, "bold"), text_color=C["texto"]).pack(side="left", padx=12)
        self.badge_total = ctk.CTkLabel(cab2, text="", font=fonte(13), fg_color=C["destaque"],
                                        text_color="#a5a8ff", corner_radius=14, height=32)
        self.badge_total.pack(side="right")

        caixa_lista, self.lista = tabela(
            batidas, [("hora", "Hora", 80, "center"), ("nome", "Nome", 200, "w"), ("tipo", "Tipo", 130, "w")]
        )
        caixa_lista.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.vazio = ctk.CTkFrame(caixa_lista, fg_color=C["cartao2"])
        ctk.CTkLabel(self.vazio, text="", image=icone("relogio", C["suave"], 56)).pack()
        ctk.CTkLabel(self.vazio, text="Nenhum registro encontrado", font=fonte(14), text_color=C["suave"]).pack(pady=(8, 0))

    def status(self, tipo, titulo, corpo=""):
        novo = (tipo, titulo, corpo)
        if novo != self.status_atual:
            self.status_atual = novo
            self.cartao_status.definir(tipo, titulo, corpo)

    def status_padrao(self):
        self.status("neutro", "Pronto para registrar", "Olhe para a câmera para registrar o seu ponto.")

    def badge_camera(self, estado):
        if estado != self.badge_atual:
            self.badge_atual = estado
            texto, fundo, cor = BADGES[estado]
            self.badge.configure(text=f"  {texto}  ", fg_color=fundo, text_color=cor)

    def mensagem(self, tipo, titulo, corpo, segundos):
        self.estado = "mensagem"
        self.msg_ate = time.time() + segundos
        self.candidato = None
        self.conta = 0
        self.status(tipo, titulo, corpo)

    def atualizar_relogio(self):
        agora = datetime.now()
        self.relogio.atualizar(agora.strftime("%H:%M:%S"), f"{DIAS[agora.weekday()]}, {agora:%d/%m/%Y}")
        self.root.after(1000, self.atualizar_relogio)

    def atualizar_lista(self):
        linhas = self.banco.registros_do_dia(date.today())
        self.lista.delete(*self.lista.get_children())
        for linha in linhas:
            self.lista.insert("", "end", values=linha)
        n = len(linhas)
        self.badge_total.configure(text=f"  {n} registro{'s' if n != 1 else ''}  ")
        if n:
            self.vazio.place_forget()
        else:
            self.vazio.place(relx=0.5, rely=0.55, anchor="center")

    # ---------- câmera + reconhecimento ----------
    def loop(self):
        frame = self.camera.ler()
        self.frame_atual = frame
        if frame is None:
            self.video.mostrar(None)
            self.badge_camera("conectando" if self.camera.estado == "conectando" else "erro")
            if self.camera.erro and not self.pausado:
                self.status("info" if self.camera.estado == "conectando" else "erro", *self.camera.erro)
                self.erro_camera_visivel = True
        else:
            self.badge_camera("ativa")
            if self.erro_camera_visivel:
                self.erro_camera_visivel = False
                self.status_padrao()
            exibir = frame.copy()
            if not self.pausado:
                try:
                    self.processar(frame, exibir)
                except cv2.error as e:
                    print("Erro no reconhecimento:", e)
            self.video.mostrar(exibir)
        self.root.after(30, self.loop)

    def processar(self, frame, exibir):
        agora = time.time()
        limiar = float(self.cfg["limiar"])
        faces = self.rosto.detectar(frame)
        face = faces[0] if faces else None
        if face is not None:
            desenhar_rosto(exibir, face, (200, 200, 200))

        if self.estado == "mensagem":
            if agora < self.msg_ate:
                return
            self.estado = "aguardando"
            self.status_padrao()

        if self.estado == "aguardando":
            if face is None:
                self.conta, self.candidato, self.desconhecido = 0, None, 0
                self.status_padrao()
                return
            if face[2] < 90:
                self.status("neutro", "Aproxime-se da câmera", "Seu rosto precisa ficar maior na imagem.")
                return
            fid, sim = self.banco.identificar(self.rosto.embedding(frame, face))
            if fid is None or sim < limiar:
                desenhar_rosto(exibir, face, (0, 0, 220))
                self.conta, self.candidato = 0, None
                self.desconhecido += 1
                if self.desconhecido >= 10:
                    self.status("erro", "Rosto não reconhecido", "Se você é novo, peça seu cadastro ao RH.")
                return
            self.desconhecido = 0
            desenhar_rosto(exibir, face, (0, 200, 0))
            if fid == self.candidato:
                self.conta += 1
            else:
                self.candidato, self.conta = fid, 1
            if self.conta < 3:  # confirma em alguns quadros seguidos antes de aceitar
                return

            self.conta = 0
            nome = self.banco.nomes[fid]
            ultima = self.banco.ultima_batida(fid)
            if ultima and (datetime.now() - ultima).total_seconds() < float(self.cfg["intervalo_min"]) * 60:
                self.mensagem("aviso", f"Ponto já registrado, {nome.split()[0]}",
                              f"Sua última batida foi às {ultima:%H:%M}. Aguarde alguns minutos.", 4)
                return
            if self.cfg["prova_de_vida"]:
                self.estado = "desafio"
                self.desafio_inicio = agora
                self.virou = False
                self.status("info", f"Olá, {nome.split()[0]}!",
                            "Vire o rosto devagar para um lado e depois volte a olhar para a câmera.")
                return
            self.bater(fid, sim)

        elif self.estado == "desafio":
            if agora - self.desafio_inicio > 8:
                bip(False)
                self.mensagem("erro", "Prova de vida não concluída", "Tente novamente.", 3)
                return
            if face is None:
                return
            giro = abs(self.rosto.giro(face))
            if giro > 0.35:
                self.virou = True
                self.status("info", "Ótimo!", "Agora olhe de frente para a câmera.")
            elif self.virou and giro < 0.15:
                fid, sim = self.banco.identificar(self.rosto.embedding(frame, face))
                if fid == self.candidato and sim >= limiar:
                    self.bater(fid, sim)

    def bater(self, fid, sim):
        tipo, quando = self.banco.registrar(fid, sim)
        nome = self.banco.nomes[fid]
        bip(True)
        self.mensagem("ok", f"Ponto registrado: {tipo}", f"{nome}\n{quando:%d/%m/%Y  •  %H:%M}", 4)
        self.atualizar_lista()

    # ---------- administração ----------
    def exigir_admin(self):
        if time.time() < self.admin_ate:
            return True
        dialogo = DialogoSenha(self.root, str(self.cfg["senha_admin"]))
        self.root.wait_window(dialogo)
        if dialogo.aprovado:
            self.admin_ate = time.time() + 300  # 5 minutos sem pedir de novo
        return dialogo.aprovado

    def abrir_cadastro(self):
        if self.exigir_admin():
            JanelaCadastro(self)

    def abrir_funcionarios(self):
        if self.exigir_admin():
            JanelaFuncionarios(self)

    def abrir_relatorio(self):
        if self.exigir_admin():
            JanelaRelatorio(self)

    def abrir_config(self):
        if self.exigir_admin():
            JanelaConfig(self)

    def trocar_camera(self):
        self.camera.parar()
        self.camera = Camera(self.cfg["camera"], self.cfg["espelhar"])
        self.camera.iniciar()

    def sair(self):
        self.camera.parar()
        self.root.destroy()


# --------------------------------------------------------------------------- #
# Janelas
# --------------------------------------------------------------------------- #
class Janela(ctk.CTkToplevel):
    def __init__(self, app, titulo):
        super().__init__(app.root, fg_color=C["fundo"])
        self.app = app
        self.title(titulo)
        self.transient(app.root)
        self.after(200, self._trazer)

    def _trazer(self):
        self.lift()
        self.focus_force()


class DialogoSenha(ctk.CTkToplevel):
    def __init__(self, root, senha_correta):
        super().__init__(root, fg_color=C["fundo"])
        self.senha_correta = senha_correta
        self.aprovado = False
        self.title("Acesso restrito")
        self.resizable(False, False)
        self.transient(root)

        corpo = cartao(self)
        corpo.pack(padx=20, pady=20)
        ctk.CTkLabel(corpo, text="", image=icone("cadeado", C["primaria_clara"], 28), width=56, height=56,
                     fg_color=C["destaque"], corner_radius=14).pack(pady=(24, 10))
        ctk.CTkLabel(corpo, text="Acesso restrito", font=fonte(18, "bold"), text_color=C["texto"]).pack()
        ctk.CTkLabel(corpo, text="Digite a senha do administrador", font=fonte(13), text_color=C["suave"]).pack(pady=(0, 12))
        self.entrada = ctk.CTkEntry(corpo, show="•", width=260, height=40, fg_color=C["interno"],
                                    border_color=C["borda"], text_color=C["texto"], font=fonte(14))
        self.entrada.pack(padx=30)
        self.lbl_erro = ctk.CTkLabel(corpo, text="", text_color=C["vermelho"], font=fonte(12), height=20)
        self.lbl_erro.pack(pady=(4, 4))
        botoes = ctk.CTkFrame(corpo, fg_color="transparent")
        botoes.pack(pady=(0, 24))
        botao(botoes, "Entrar", self.confirmar, "primario", width=125).pack(side="left", padx=(0, 10))
        botao(botoes, "Cancelar", self.destroy, "secundario", width=125).pack(side="left")

        self.entrada.bind("<Return>", lambda e: self.confirmar())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(150, self._focar)

    def _focar(self):
        self.lift()
        self.focus_force()
        self.entrada.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def confirmar(self):
        if self.entrada.get() == self.senha_correta:
            self.aprovado = True
            self.destroy()
        else:
            self.lbl_erro.configure(text="Senha incorreta.")
            self.entrada.delete(0, "end")


class JanelaCadastro(Janela):
    AMOSTRAS = 5

    def __init__(self, app):
        super().__init__(app, "Cadastrar funcionário")
        self.resizable(False, False)
        app.pausado = True
        app.status("info", "Cadastro em andamento", "O registro de ponto fica pausado enquanto o cadastro estiver aberto.")
        self.amostras = []
        self.capturando = False
        self.ultima_amostra = 0.0
        self.biometria = None

        esq = cartao(self)
        esq.pack(side="left", fill="both", padx=(20, 10), pady=20)
        ctk.CTkLabel(esq, text="Captura do rosto", font=fonte(16, "bold"), text_color=C["texto"]).pack(
            anchor="w", padx=20, pady=(16, 10))
        caixa = ctk.CTkFrame(esq, fg_color=C["interno"], corner_radius=14, border_width=1, border_color=C["borda"])
        caixa.pack(padx=16, pady=(0, 16))
        self.video = PainelVideo(caixa, width=px(520), height=px(390))
        self.video.pack(padx=px(6), pady=px(6))

        dir_ = cartao(self)
        dir_.pack(side="left", fill="both", padx=(10, 20), pady=20)
        ctk.CTkLabel(dir_, text="Dados do funcionário", font=fonte(16, "bold"), text_color=C["texto"]).pack(
            anchor="w", padx=20, pady=(16, 12))
        self.var_nome = tk.StringVar()
        self.var_matricula = tk.StringVar()
        self.var_cpf = tk.StringVar()
        self.var_lgpd = tk.BooleanVar()
        campo(dir_, "Nome completo *", self.var_nome)
        campo(dir_, "Matrícula *", self.var_matricula)
        campo(dir_, "CPF", self.var_cpf)

        ctk.CTkLabel(dir_, text="Peça para o funcionário olhar para a câmera e mexer levemente a cabeça durante a captura.",
                     wraplength=300, justify="left", font=fonte(12), text_color=C["suave"]).pack(anchor="w", padx=20, pady=(4, 10))
        self.btn_capturar = botao(dir_, "Capturar rosto", self.iniciar_captura, "primario", "camera")
        self.btn_capturar.pack(anchor="w", padx=20)
        self.barra = ctk.CTkProgressBar(dir_, width=300, progress_color=C["primaria"], fg_color=C["interno"])
        self.barra.set(0)
        self.barra.pack(anchor="w", padx=20, pady=(12, 4))
        self.lbl_progresso = ctk.CTkLabel(dir_, text="Nenhuma captura ainda.", font=fonte(12), text_color=C["suave"])
        self.lbl_progresso.pack(anchor="w", padx=20)

        ctk.CTkCheckBox(
            dir_, text="O funcionário foi informado e autorizou\no uso da biometria facial (LGPD)",
            variable=self.var_lgpd, font=fonte(12), text_color=C["texto"], fg_color=C["primaria"],
            hover_color=C["primaria2"], border_color=C["borda"],
        ).pack(anchor="w", padx=20, pady=16)

        botoes = ctk.CTkFrame(dir_, fg_color="transparent")
        botoes.pack(anchor="w", padx=20, pady=(0, 20))
        botao(botoes, "Salvar", self.salvar, "sucesso", "salvar", width=140).pack(side="left", padx=(0, 10))
        botao(botoes, "Cancelar", self.fechar, "secundario", width=140).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.atualizar()

    def progresso(self, texto, cor):
        self.lbl_progresso.configure(text=texto, text_color=cor)

    def iniciar_captura(self):
        if self.app.frame_atual is None:
            self.progresso("Sem imagem da câmera. Conecte a câmera em Configurações.", C["vermelho"])
            messagebox.showwarning(
                "Sem câmera",
                "O programa não está recebendo imagem da câmera.\n\n"
                "Feche o cadastro, abra Configurações e coloque a câmera do celular\n"
                "(ex.: 1 para DroidCam/Iriun, ou http://IP-DO-CELULAR:4747/video).",
                parent=self,
            )
            return
        self.amostras = []
        self.biometria = None
        self.capturando = True
        self.barra.set(0)
        self.btn_capturar.configure(state="disabled")
        self.progresso("Capturando...", C["primaria_clara"])

    def atualizar(self):
        if not self.winfo_exists():
            return
        frame = self.app.frame_atual
        if frame is None:
            self.video.mostrar(None)
            if self.capturando:
                self.progresso("Sem imagem da câmera. Aguardando...", C["vermelho"])
        else:
            exibir = frame.copy()
            try:
                faces = self.app.rosto.detectar(frame)
            except cv2.error:
                faces = []
            for f in faces:
                desenhar_rosto(exibir, f, (0, 200, 0) if len(faces) == 1 else (0, 0, 220))
            if self.capturando:
                self.capturar(frame, faces)
            self.video.mostrar(exibir)
        self.after(40, self.atualizar)

    def capturar(self, frame, faces):
        if len(faces) != 1:
            self.progresso("Deixe apenas UM rosto na frente da câmera.", C["vermelho"])
            return
        if faces[0][2] < 100:
            self.progresso("Aproxime o rosto da câmera.", "#fbbf24")
            return
        if time.time() - self.ultima_amostra < 0.4:
            return
        self.ultima_amostra = time.time()
        self.amostras.append(self.app.rosto.embedding(frame, faces[0]))
        self.barra.set(len(self.amostras) / self.AMOSTRAS)
        self.progresso(f"Amostra {len(self.amostras)} de {self.AMOSTRAS}", C["primaria_clara"])
        if len(self.amostras) >= self.AMOSTRAS:
            self.finalizar_captura()

    def finalizar_captura(self):
        self.capturando = False
        self.btn_capturar.configure(state="normal", text="Capturar novamente")
        media = np.mean(self.amostras, axis=0)
        media /= np.linalg.norm(media)
        if min(float(a @ media) for a in self.amostras) < 0.5:
            self.progresso("Capturas inconsistentes. Capture novamente.", C["vermelho"])
            return
        fid, sim = self.app.banco.identificar(media)
        if fid is not None and sim >= float(self.app.cfg["limiar"]):
            nome = self.app.banco.nomes[fid]
            if not messagebox.askyesno(
                "Rosto já cadastrado",
                f"Este rosto é muito parecido com o de {nome}, que já está cadastrado.\n\nCadastrar mesmo assim?",
                parent=self,
            ):
                self.progresso("Captura descartada.", C["vermelho"])
                return
        self.biometria = media.astype(np.float32)
        self.progresso("✔ Rosto capturado com sucesso!", "#4ade80")

    def salvar(self):
        nome = " ".join(self.var_nome.get().split())
        matricula = self.var_matricula.get().strip()
        cpf = "".join(c for c in self.var_cpf.get() if c.isdigit())
        if not nome or not matricula:
            messagebox.showwarning("Cadastro", "Preencha o nome e a matrícula.", parent=self)
            return
        if cpf and len(cpf) != 11:
            messagebox.showwarning("Cadastro", "O CPF deve ter 11 números.", parent=self)
            return
        if self.biometria is None:
            messagebox.showwarning("Cadastro", "Capture o rosto do funcionário antes de salvar.", parent=self)
            return
        if not self.var_lgpd.get():
            messagebox.showwarning("Cadastro", "Confirme a autorização do uso da biometria (LGPD).", parent=self)
            return
        try:
            self.app.banco.cadastrar(matricula, nome, cpf or None, self.biometria)
        except sqlite3.IntegrityError:
            messagebox.showerror("Cadastro", f"Já existe um funcionário com a matrícula {matricula}.", parent=self)
            return
        messagebox.showinfo("Cadastro", f"{nome} cadastrado com sucesso!", parent=self)
        self.fechar()

    def fechar(self):
        self.app.pausado = False
        self.app.status_padrao()
        self.destroy()


class JanelaFuncionarios(Janela):
    def __init__(self, app):
        super().__init__(app, "Funcionários")
        self.geometry("900x540")

        c = cartao(self)
        c.pack(fill="both", expand=True, padx=20, pady=20)
        cab = ctk.CTkFrame(c, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(16, 12))
        ctk.CTkLabel(cab, text="", image=icone("pessoas", C["primaria_clara"], 26), width=30).pack(side="left")
        ctk.CTkLabel(cab, text="Funcionários cadastrados", font=fonte(18, "bold"), text_color=C["texto"]).pack(
            side="left", padx=12)

        caixa, self.tabela = tabela(c, [
            ("matricula", "Matrícula", 100, "center"), ("nome", "Nome", 250, "w"), ("cpf", "CPF", 130, "center"),
            ("criado", "Cadastrado em", 140, "center"), ("situacao", "Situação", 100, "center"),
        ])
        caixa.pack(fill="both", expand=True, padx=16)

        botoes = ctk.CTkFrame(c, fg_color="transparent")
        botoes.pack(fill="x", padx=16, pady=16)
        botao(botoes, "Desligar funcionário (apaga a biometria)", self.desligar, "perigo", "lixeira").pack(side="left")
        botao(botoes, "Fechar", self.destroy, "secundario", width=120).pack(side="right")
        self.carregar()

    def carregar(self):
        self.tabela.delete(*self.tabela.get_children())
        for fid, matricula, nome, cpf, criado, ativo in self.app.banco.listar_funcionarios():
            cpf_fmt = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if cpf else ""
            criado_fmt = datetime.strptime(criado, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
            self.tabela.insert("", "end", iid=str(fid),
                               values=(matricula, nome, cpf_fmt, criado_fmt, "Ativo" if ativo else "Desligado"))

    def desligar(self):
        sel = self.tabela.selection()
        if not sel:
            messagebox.showinfo("Funcionários", "Selecione um funcionário na lista.", parent=self)
            return
        nome = self.tabela.item(sel[0])["values"][1]
        if messagebox.askyesno(
            "Desligar funcionário",
            f"Desligar {nome}?\n\nA biometria facial será apagada e ele não conseguirá mais bater ponto.\n"
            "As batidas antigas continuam guardadas para os relatórios.",
            parent=self,
        ):
            self.app.banco.desativar(int(sel[0]))
            self.carregar()


class JanelaRelatorio(Janela):
    def __init__(self, app):
        super().__init__(app, "Relatório de ponto")
        self.resizable(False, False)

        hoje = date.today()
        self.var_ini = tk.StringVar(value=hoje.replace(day=1).strftime("%d/%m/%Y"))
        self.var_fim = tk.StringVar(value=hoje.strftime("%d/%m/%Y"))

        c = cartao(self)
        c.pack(padx=20, pady=20)
        cab = ctk.CTkFrame(c, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(cab, text="", image=icone("doc", C["verde"], 26), width=30).pack(side="left")
        ctk.CTkLabel(cab, text="Relatório de ponto", font=fonte(18, "bold"), text_color=C["texto"]).pack(side="left", padx=12)
        ctk.CTkLabel(c, text="Escolha o período e exporte para o Excel.", font=fonte(13), text_color=C["suave"]).pack(
            anchor="w", padx=20, pady=(0, 12))

        datas = ctk.CTkFrame(c, fg_color="transparent")
        datas.pack(anchor="w")
        col1 = ctk.CTkFrame(datas, fg_color="transparent")
        col1.pack(side="left")
        col2 = ctk.CTkFrame(datas, fg_color="transparent")
        col2.pack(side="left")
        campo(col1, "Data inicial", self.var_ini, largura=160, placeholder_text="dd/mm/aaaa")
        campo(col2, "Data final", self.var_fim, largura=160, placeholder_text="dd/mm/aaaa")
        botao(c, "Exportar para Excel", self.exportar, "sucesso", "doc").pack(anchor="w", padx=20, pady=(6, 20))

    def exportar(self):
        try:
            ini = datetime.strptime(self.var_ini.get().strip(), "%d/%m/%Y").date()
            fim = datetime.strptime(self.var_fim.get().strip(), "%d/%m/%Y").date()
        except ValueError:
            messagebox.showwarning("Relatório", "Digite as datas no formato dd/mm/aaaa.", parent=self)
            return
        if fim < ini:
            messagebox.showwarning("Relatório", "A data final é antes da inicial.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"ponto_{ini:%Y-%m-%d}_a_{fim:%Y-%m-%d}.xlsx",
        )
        if not caminho:
            return
        try:
            gerar_excel(self.app.banco, ini, fim, caminho)
        except ValueError as e:
            messagebox.showinfo("Relatório", str(e), parent=self)
            return
        except PermissionError:
            messagebox.showerror("Relatório", "Não foi possível salvar. O arquivo está aberto no Excel?", parent=self)
            return
        if messagebox.askyesno("Relatório", "Relatório gerado! Deseja abrir agora?", parent=self):
            os.startfile(caminho)


class JanelaConfig(Janela):
    def __init__(self, app):
        super().__init__(app, "Configurações")
        self.resizable(False, False)
        cfg = app.cfg

        self.var_camera = tk.StringVar(value=str(cfg["camera"]))
        self.var_espelhar = tk.BooleanVar(value=cfg["espelhar"])
        self.var_vida = tk.BooleanVar(value=cfg["prova_de_vida"])
        self.var_limiar = tk.StringVar(value=str(cfg["limiar"]))
        self.var_intervalo = tk.StringVar(value=str(cfg["intervalo_min"]))
        self.var_senha = tk.StringVar(value=str(cfg["senha_admin"]))

        c = cartao(self)
        c.pack(padx=20, pady=20)
        cab = ctk.CTkFrame(c, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(16, 12))
        ctk.CTkLabel(cab, text="", image=icone("config", C["primaria_clara"], 26), width=30).pack(side="left")
        ctk.CTkLabel(cab, text="Configurações", font=fonte(18, "bold"), text_color=C["texto"]).pack(side="left", padx=12)

        campo(c, "Câmera", self.var_camera, largura=420)
        dica = ctk.CTkFrame(c, fg_color=C["interno"], corner_radius=10)
        dica.pack(anchor="w", fill="x", padx=20, pady=(0, 14))
        ctk.CTkLabel(dica, justify="left", font=fonte(12), text_color=C["suave"], text=(
            "0   →  webcam do computador\n"
            "1 ou 2   →  celular pelo programa DroidCam / Iriun no PC\n"
            "http://IP-DO-CELULAR:4747/video   →  app DroidCam pelo Wi-Fi\n"
            "http://IP-DO-CELULAR:8080/video   →  app IP Webcam pelo Wi-Fi\n"
            "(o IP aparece na tela do app no celular)"
        )).pack(anchor="w", padx=14, pady=10)

        for texto, var in [("Espelhar imagem", self.var_espelhar),
                           ("Prova de vida (pedir para virar o rosto)", self.var_vida)]:
            ctk.CTkSwitch(c, text=texto, variable=var, font=fonte(13), text_color=C["texto"],
                          progress_color=C["primaria"], fg_color=C["borda"]).pack(anchor="w", padx=20, pady=4)

        grade = ctk.CTkFrame(c, fg_color="transparent")
        grade.pack(anchor="w", padx=20, pady=(12, 8))
        for i, (texto, var, extra) in enumerate([
            ("Rigor do reconhecimento (0.30 a 0.60)", self.var_limiar, {}),
            ("Minutos mínimos entre batidas", self.var_intervalo, {}),
            ("Senha do administrador", self.var_senha, {"show": "•"}),
        ]):
            ctk.CTkLabel(grade, text=texto, font=fonte(13), text_color=C["suave"]).grid(row=i, column=0, sticky="w", pady=4)
            ctk.CTkEntry(grade, textvariable=var, width=110, height=34, fg_color=C["interno"], border_color=C["borda"],
                         text_color=C["texto"], font=fonte(13), **extra).grid(row=i, column=1, padx=(16, 0), pady=4)

        botoes = ctk.CTkFrame(c, fg_color="transparent")
        botoes.pack(anchor="w", padx=20, pady=(8, 20))
        botao(botoes, "Salvar e aplicar", self.salvar, "primario", "salvar").pack(side="left", padx=(0, 10))
        botao(botoes, "Cancelar", self.destroy, "secundario", width=120).pack(side="left")

    def salvar(self):
        try:
            limiar = float(self.var_limiar.get().replace(",", "."))
            intervalo = float(self.var_intervalo.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Configurações", "Rigor e minutos devem ser números.", parent=self)
            return
        if not 0.2 <= limiar <= 0.8:
            messagebox.showwarning("Configurações", "O rigor deve ficar entre 0.20 e 0.80.", parent=self)
            return
        if not self.var_senha.get().strip():
            messagebox.showwarning("Configurações", "A senha não pode ficar vazia.", parent=self)
            return
        cfg = self.app.cfg
        camera_mudou = (self.var_camera.get().strip() != str(cfg["camera"])
                        or self.var_espelhar.get() != cfg["espelhar"])
        cfg.update(
            camera=self.var_camera.get().strip() or "0",
            espelhar=self.var_espelhar.get(),
            prova_de_vida=self.var_vida.get(),
            limiar=limiar,
            intervalo_min=intervalo,
            senha_admin=self.var_senha.get().strip(),
        )
        salvar_config(cfg)
        if camera_mudou:
            self.app.trocar_camera()
        self.destroy()


# --------------------------------------------------------------------------- #
# Relatório Excel
# --------------------------------------------------------------------------- #
def fmt_minutos(m):
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


def gerar_excel(banco, inicio, fim, caminho):
    import pandas as pd

    linhas = banco.registros_periodo(inicio, fim)
    if not linhas:
        raise ValueError("Nenhuma batida de ponto encontrada nesse período.")

    df = pd.DataFrame(linhas, columns=["Matrícula", "Nome", "DataHora", "Tipo"])
    df["DataHora"] = pd.to_datetime(df["DataHora"])
    df["Dia"] = df["DataHora"].dt.date

    batidas = pd.DataFrame({
        "Matrícula": df["Matrícula"],
        "Nome": df["Nome"],
        "Data": df["DataHora"].dt.strftime("%d/%m/%Y"),
        "Hora": df["DataHora"].dt.strftime("%H:%M:%S"),
        "Tipo": df["Tipo"],
    })

    resumo, totais = [], {}
    for (matricula, nome, dia), grupo in df.groupby(["Matrícula", "Nome", "Dia"], sort=True):
        horarios = sorted(grupo["DataHora"])
        # soma os intervalos trabalhados: (entrada → saída almoço) + (volta → saída) + ...
        minutos = sum(
            (horarios[i + 1] - horarios[i]).total_seconds() / 60 for i in range(0, len(horarios) - 1, 2)
        )
        cols = [h.strftime("%H:%M") for h in horarios[:4]] + [""] * (4 - min(4, len(horarios)))
        obs = "Batidas ímpares - verificar" if len(horarios) % 2 else ""
        if len(horarios) > 4:
            obs = (obs + "; " if obs else "") + f"{len(horarios) - 4} batida(s) extra(s)"
        resumo.append([matricula, nome, dia.strftime("%d/%m/%Y"), *cols, fmt_minutos(minutos), obs])
        chave = (matricula, nome)
        dias, total = totais.get(chave, (0, 0.0))
        totais[chave] = (dias + 1, total + minutos)

    df_resumo = pd.DataFrame(resumo, columns=["Matrícula", "Nome", "Data", *TIPOS, "Horas trabalhadas", "Observação"])
    df_totais = pd.DataFrame(
        [[m, n, d, fmt_minutos(t)] for (m, n), (d, t) in totais.items()],
        columns=["Matrícula", "Nome", "Dias trabalhados", "Total de horas"],
    )

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        for nome_aba, tab in [("Resumo por dia", df_resumo), ("Total por funcionário", df_totais),
                              ("Todas as batidas", batidas)]:
            tab.to_excel(writer, sheet_name=nome_aba, index=False)
            aba = writer.sheets[nome_aba]
            for i, col in enumerate(tab.columns):
                largura = max([len(str(col))] + [len(str(v)) for v in tab[col]]) + 2
                aba.column_dimensions[aba.cell(row=1, column=i + 1).column_letter].width = min(largura, 45)
            aba.freeze_panes = "A2"


# --------------------------------------------------------------------------- #
def main():
    global ESCALA
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    ESCALA = root.winfo_fpixels("1i") / 96
    try:
        baixar_modelos(root)
        rosto = Rosto()
    except Exception as e:
        messagebox.showerror("Ponto Facial", str(e))
        root.destroy()
        return
    cfg = carregar_config()
    banco = Banco(ARQ_DB)
    root.deiconify()
    root.after(0, lambda: root.state("zoomed"))
    App(root, cfg, banco, rosto)
    root.mainloop()


if __name__ == "__main__":
    main()
