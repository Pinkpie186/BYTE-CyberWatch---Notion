"""
╔══════════════════════════════════════════════════════════════╗
║       BYTE v2 — CyberWatch Automation Script                 ║
║   RSS Feeds → Banco de Notícias → Card BYTE no Notion        ║
╚══════════════════════════════════════════════════════════════╝

Este arquivo é a versão pública/segura do BYTE CyberWatch.

Ele não contém tokens, chaves de API ou IDs reais.
Configure as variáveis no arquivo .env local ou nos Secrets do GitHub Actions.

INSTALAÇÃO:
    pip install -r requirements.txt

EXECUÇÃO:
    python cyber_watcher.py

VARIÁVEIS DE AMBIENTE:
    NOTION_TOKEN=
    NOTION_DATABASE_ID=
    NOTION_BYTE_DB_ID=
    CRITICAL_VIEW_URL=

ARQUIVO DE FONTES:
    config/feeds.json
"""

import os
import json
import random
import re
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import Counter
from zoneinfo import ZoneInfo

import feedparser
from notion_client import Client
from dotenv import load_dotenv


# ==============================================================
# CONFIGURAÇÕES GERAIS
# ==============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
FEEDS_FILE = BASE_DIR / "config" / "feeds.json"

BR_TZ = ZoneInfo("America/Sao_Paulo")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("byte_cyberwatch")

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NEWS_DB_ID = os.getenv("NOTION_DATABASE_ID", "")
BYTE_DB_ID = os.getenv("NOTION_BYTE_DB_ID", "")
CRITICAL_VIEW_URL = os.getenv("CRITICAL_VIEW_URL", "")


# ==============================================================
# REGRAS DE FILTRO, CATEGORIA, TAGS, TEMA E TIPO DE SINAL
# ==============================================================

CYBER_KEYWORDS = [
    # Cyber clássico
    "vulnerability", "exploit", "malware", "ransomware", "phishing", "breach", "hack",
    "cybersecurity", "cyber", "security", "CVE", "zero-day", "threat", "attack", "APT",
    "trojan", "botnet", "DDoS", "patch", "CISO", "infosec", "incident", "data leak",
    "vulnerabilidade", "segurança", "ataque", "vazamento", "osint", "investigation",

    # AI & Data
    "ai", "artificial intelligence", "machine learning", "llm", "data analysis",
    "python", "pandas", "algorithm", "dataset", "inteligência artificial", "dados",

    # Geopolítica & Finanças
    "geopolitics", "investing", "trading", "market", "economy", "brazil", "latam",
    "government", "policy", "sanctions", "mercado", "geopolítica",

    # Engenharia & Arquitetura
    "system design", "architecture", "backend", "frontend", "developer", "cloud",
    "kubernetes", "docker", "api", "software", "engenharia", "arquitetura",
]

CATEGORY_RULES = {
    "Vulnerabilidade": ["vulnerability", "CVE", "zero-day", "exploit", "patch", "RCE", "CVSS"],
    "Malware/Ransomware": ["malware", "ransomware", "trojan", "botnet", "spyware", "worm"],
    "Threat Intelligence": ["APT", "threat actor", "threat intelligence", "TTP", "IOC", "hack", "breach"],
    "Políticas & Regulação": ["regulation", "compliance", "GDPR", "LGPD", "ANPD", "policy", "law"],
    "Incidente": ["incident", "data leak", "outage"],
    "Privacidade": ["privacy", "data protection", "personal data"],
    "Engenharia & Arquitetura": ["system design", "architecture", "backend", "frontend", "developer", "api"],
    "AI & Dados": ["AI", "machine learning", "data analysis", "python", "pandas", "LLM", "algorithm"],
    "Geopolítica & OSINT": ["geopolitics", "osint", "investigation", "government", "sanctions", "war", "brazil"],
    "Mercado & Negócios": ["investing", "trading", "market", "economy", "business"],
}

TAG_RULES = {
    "Zero-day": ["zero-day", "0-day"],
    "APT": ["APT", "nation-state", "state-sponsored"],
    "Ransomware": ["ransomware", "ransom"],
    "Phishing": ["phishing", "BEC"],
    "AI": ["AI", "LLM", "machine learning", "artificial intelligence"],
    "Cloud": ["cloud", "AWS", "Azure", "GCP", "kubernetes", "docker"],
    "IoT": ["IoT", "OT", "ICS", "SCADA"],
    "Critical Infrastructure": ["infrastructure", "energy", "power grid", "water", "healthcare"],
    "Python": ["python", "pandas", "django", "flask"],
    "OSINT": ["osint", "open source intelligence", "reconnaissance"],
}

THREAT_SIGNAL_RULES = {
    "🚨 Ameaça Real": [
        "actively exploited", "active exploitation", "exploited in attacks",
        "breach", "data leak", "ransomware attack", "malware campaign",
        "zero-day", "cve", "critical flaw", "remote code execution",
        "apt", "phishing campaign", "botnet", "ddos", "wiper",
        "hackers exploit", "stolen", "compromised", "incident",
    ],
    "🧠 Análise / Pesquisa": [
        "research", "analysis", "report", "study", "findings",
        "trend", "lessons", "whitepaper", "guidance", "framework",
    ],
    "🎓 Conteúdo Educacional": [
        "how to", "tutorial", "guide", "roadmap", "learn",
        "tips", "explained", "course", "workshop",
    ],
}

THEME_RULES = {
    "Cyber": [
        "cyber", "security", "vulnerability", "cve", "exploit",
        "malware", "ransomware", "phishing", "breach", "apt",
        "zero-day", "threat", "attack",
    ],
    "AI": [
        "ai", "llm", "machine learning", "artificial intelligence",
        "model", "agent", "automation",
    ],
    "Dev": [
        "python", "backend", "frontend", "software",
        "architecture", "system design", "api", "developer",
    ],
    "Geo": [
        "geopolitics", "brazil", "china", "russia",
        "government", "policy", "state",
    ],
    "Finance": [
        "trading", "investing", "market",
        "crypto", "bitcoin", "finance",
    ],
}


# ==============================================================
# FUNÇÕES DE APOIO
# ==============================================================

def now_br() -> datetime:
    return datetime.now(BR_TZ)


def today_br() -> str:
    return now_br().date().isoformat()


def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()[:500]


def is_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(keyword.lower() in text for keyword in CYBER_KEYWORDS)


def get_cats(title: str, summary: str) -> list[str]:
    text = (title + " " + summary).lower()
    found = [
        category
        for category, keywords in CATEGORY_RULES.items()
        if any(keyword.lower() in text for keyword in keywords)
    ]
    return found or ["Threat Intelligence"]


def get_tags(title: str, summary: str) -> list[str]:
    text = (title + " " + summary).lower()
    return [
        tag
        for tag, keywords in TAG_RULES.items()
        if any(keyword.lower() in text for keyword in keywords)
    ][:4]


def get_themes(title: str, summary: str, source: str = "") -> list[str]:
    text = f"{title} {summary} {source}".lower()
    found = [
        theme
        for theme, keywords in THEME_RULES.items()
        if any(keyword.lower() in text for keyword in keywords)
    ]
    return found or ["Geral"]


def classify_signal_type(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()

    for signal_type, keywords in THREAT_SIGNAL_RULES.items():
        if any(keyword.lower() in text for keyword in keywords):
            return signal_type

    return "📰 Notícia Geral"


def threat_level(highlights: int) -> str:
    if highlights >= 7:
        return "🔴 CRÍTICO"
    if highlights >= 4:
        return "🟠 ALTO"
    if highlights >= 2:
        return "🟡 MÉDIO"
    return "🟢 BAIXO"


def status_agent(level: str) -> str:
    if level == "🔴 CRÍTICO":
        return "🔴 Vigilância Máxima"
    if level == "🟠 ALTO":
        return "🟠 Atenção Reforçada"
    if level == "🟡 MÉDIO":
        return "🟡 Monitoramento Preventivo"
    return "🟢 Online"


def get_cover_by_level(level: str) -> str:
    """
    URLs públicas usadas como capas externas no Notion.

    Você pode trocar por imagens próprias hospedadas em uma URL pública.
    """
    if "CRÍTICO" in level:
        return "https://i.pinimg.com/736x/4d/c2/0f/4dc20f8123f12c863e6e488d1999bcf4.jpg"
    if "ALTO" in level:
        return "https://i.pinimg.com/1200x/43/c8/51/43c8516d4d133e1426350b934e9455c2.jpg"
    if "MÉDIO" in level:
        return "https://i.pinimg.com/1200x/c5/ac/d3/c5acd393a2eaf2898999b6a80fc64090.jpg"
    return "https://i.pinimg.com/1200x/33/ce/9a/33ce9aeda995ccca617218bbfcc3ae70.jpg"


def validate_environment() -> bool:
    required_vars = {
        "NOTION_TOKEN": NOTION_TOKEN,
        "NOTION_DATABASE_ID": NEWS_DB_ID,
        "NOTION_BYTE_DB_ID": BYTE_DB_ID,
    }

    missing = [name for name, value in required_vars.items() if not value]

    if missing:
        log.error("Variáveis de ambiente obrigatórias não definidas:")
        for name in missing:
            log.error(f"- {name}")
        log.error("Crie um arquivo .env local ou configure os Secrets no GitHub Actions.")
        return False

    if not CRITICAL_VIEW_URL:
        log.warning("CRITICAL_VIEW_URL não definido. O link de críticos será exibido como não configurado.")

    return True


def load_feeds() -> list[dict]:
    """
    Carrega as fontes RSS a partir de config/feeds.json.

    Isso permite que outras pessoas usem o projeto com suas próprias fontes
    sem precisar alterar o código principal.
    """
    if not FEEDS_FILE.exists():
        log.warning("Arquivo config/feeds.json não encontrado. Nenhuma fonte será carregada.")
        return []

    try:
        with FEEDS_FILE.open("r", encoding="utf-8") as file:
            feeds = json.load(file)

        valid_feeds = []

        for feed in feeds:
            if not feed.get("name") or not feed.get("url"):
                log.warning(f"Feed ignorado por falta de name/url: {feed}")
                continue

            valid_feeds.append(
                {
                    "name": feed["name"],
                    "url": feed["url"],
                    "source": feed.get("source", feed["name"]),
                }
            )

        return valid_feeds

    except json.JSONDecodeError as error:
        log.error(f"Erro ao ler config/feeds.json: {error}")
        return []


def notion_rich_text(text: str, limit: int = 1900) -> list[dict]:
    return [{"text": {"content": (text or "")[:limit]}}]


def formatar_notion(texto: str, cor_destaque: str) -> list[dict]:
    """
    Lê um texto com **asteriscos** e transforma em rich_text formatado para o Notion.
    Trechos entre ** ficam em negrito e recebem a cor do nível de alerta.
    """
    partes = texto.split("**")
    rich_text = []

    for i, parte in enumerate(partes):
        if not parte:
            continue

        is_bold = i % 2 != 0
        rich_text.append(
            {
                "text": {"content": parte},
                "annotations": {
                    "bold": is_bold,
                    "color": cor_destaque if is_bold else "default",
                },
            }
        )

    return rich_text


# ==============================================================
# MENSAGENS E BRIEFING
# ==============================================================

def build_terminal(stats: dict) -> str:
    agora = now_br()
    d = agora.strftime("%d.%m.%Y")
    h = agora.strftime("%H:%M")
    bar = "━" * 38

    tags_txt = ""
    for i, (tag, cnt) in enumerate(stats["top_tags"][:5], 1):
        tags_txt += f"  [{i}] {tag:<24} · {cnt} ocorrências\n"
    if not tags_txt:
        tags_txt = "  — Sem dados de tags hoje\n"

    cats_txt = ""
    emoji_map = {
        "Vulnerabilidade": "🔓",
        "Malware/Ransomware": "🦠",
        "Threat Intelligence": "🔍",
        "Políticas & Regulação": "🏛️",
        "Ferramentas & Pesquisa": "🛠️",
        "Incidente": "🚨",
        "Privacidade": "🔒",
        "AI & Dados": "🧠",
        "Geopolítica & OSINT": "🌎",
        "Mercado & Negócios": "📈",
        "Engenharia & Arquitetura": "🏗️",
    }

    for cat, cnt in stats["top_cats"][:5]:
        cats_txt += f"  {emoji_map.get(cat, '📌')} {cat}: {cnt}\n"
    if not cats_txt:
        cats_txt = "  — Sem dados de categoria hoje\n"

    src_txt = ""
    for src, cnt in stats["by_source"].items():
        blocks = "█" * min(cnt * 3, 12)
        src_txt += f"  [√] {src:<22} {blocks:<12} {cnt}\n"
    if not src_txt:
        src_txt = "  — Sem fontes ativas hoje\n"

    signal_txt = ""
    for signal, cnt in stats["signal_types"].items():
        signal_txt += f"  {signal}: {cnt}\n"
    if not signal_txt:
        signal_txt = "  — Sem classificação de sinais hoje\n"

    return (
        f"[ BYTE // DAILY REPORT // {d} // {h} BRT ]\n"
        f"{bar}\n"
        f"> TOTAL INTEL COLETADA   : {stats['total']} entradas\n"
        f"> NÍVEL DE AMEAÇA GLOBAL : {stats['level']}\n"
        f"> DESTAQUES CRÍTICOS     : {stats['highlights']}\n"
        f"> NOVAS INSERIDAS        : {stats['new_total']}\n"
        f"> REUTILIZADAS NO CICLO  : {stats['reused_total']}\n"
        f"{bar}\n\n"
        f"> TOP VETORES HOJE:\n"
        f"{tags_txt}"
        f"{bar}\n\n"
        f"> DISTRIBUIÇÃO POR CATEGORIA:\n"
        f"{cats_txt}"
        f"{bar}\n\n"
        f"> TIPO DE SINAL:\n"
        f"{signal_txt}"
        f"{bar}\n\n"
        f"> FONTES ATIVAS:\n"
        f"{src_txt}"
        f"{bar}\n"
        f"> STATUS: MONITORAMENTO ATIVO ✅\n"
    )


def build_agent_message(stats: dict) -> tuple[str, str, str]:
    current_hour = now_br().hour

    if 5 <= current_hour < 12:
        saudacoes = ["Bom dia, Giulia", "Iniciando protocolo matutino", "Sistemas online para a manhã"]
    elif 12 <= current_hour < 18:
        saudacoes = ["Boa tarde, Operadora", "Atualização de meio-dia", "Ciclo vespertino ativo"]
    else:
        saudacoes = ["Boa noite, Giulia", "Varredura de fim de turno", "Sistemas em modo noturno"]

    saudacao = random.choice(saudacoes)
    agora = now_br().strftime("%d.%m.%Y // %H:%M BRT")

    top_tags_str = " e ".join(tag for tag, _ in stats["top_tags"][:2]) or "alvos diversos"
    top_cats_str = stats["top_cats"][0][0] if stats["top_cats"] else "atividade mista"

    resumo_executivo = (
        f"{agora} ⚡ {stats['total']} eventos • "
        f"🚨 {stats['highlights']} críticos • "
        f"🧠 {top_tags_str}"
    )

    if stats["level"] == "🔴 CRÍTICO":
        mensagens = [
            f"🚨 Alerta Vermelho. Interceptei **{stats['total']}** eventos e isolei **{stats['highlights']}** ameaças de severidade máxima.\n\nO fluxo principal aponta para **{top_cats_str}** envolvendo **{top_tags_str}**. Diretriz: Análise imediata dos logs críticos exigida.",
            f"O cenário atual exige contenção. Identifiquei **{stats['highlights']}** anomalias críticas entre os **{stats['total']}** registros processados.\n\nVetores primários: **{top_tags_str}**. Acesse o painel de incidentes o quanto antes.",
            f"Protocolo de crise ativado. Varredura concluída com **{stats['total']}** itens.\n\nTemos **{stats['highlights']}** pontos de alto risco no radar, concentrados em **{top_tags_str}**. Ação de mitigação prioritária para o turno de hoje.",
        ]
    elif stats["level"] == "🟠 ALTO":
        mensagens = [
            f"⚠️ O ambiente requer atenção tática.\n\nCompilei **{stats['total']}** reportes hoje, identificando **{stats['highlights']}** incidentes críticos relacionados a **{top_tags_str}**. Diretriz: Revisar políticas de defesa correspondentes.",
            f"Nível de ameaça elevado. Temos **{stats['total']}** eventos na base, com **{stats['highlights']}** marcações de severidade em **{top_tags_str}**.\n\nMantenha vigilância nos relatórios de **{top_cats_str}** hoje.",
            f"Varredura concluída. O cenário está aquecido.\n\nRegistrei **{stats['total']}** novos dados contendo **{stats['highlights']}** pontos críticos. Recomendo postura defensiva ativa contra **{top_tags_str}**.",
        ]
    elif stats["level"] == "🟡 MÉDIO":
        mensagens = [
            f"Atenção preventiva sustentada.\n\nForam processados **{stats['total']}** eventos, contendo **{stats['highlights']}** alertas isolados de atenção. As discussões estão focadas em **{top_tags_str}**. Turno liberado para monitoramento padrão.",
            f"O perímetro requer vigilância moderada.\n\nIdentifiquei **{stats['highlights']}** pontos sensíveis entre os **{stats['total']}** registros de inteligência. O destaque do dia é **{top_cats_str}**.",
            f"Monitoramento contínuo.\n\nA varredura de **{stats['total']}** itens revelou **{stats['highlights']}** anomalias que exigem verificação. O cenário se mantém voltado para **{top_tags_str}**.",
        ]
    else:
        mensagens = [
            f"🟢 Sistemas operando em calmaria.\n\n**{stats['total']}** eventos processados com taxa mínima de anomalia (**{stats['highlights']}** críticos). Bom cenário para focar em estudo e análise profunda.",
            f"Rede estável.\n\nO fluxo de dados (**{stats['total']}** registros) possui apenas **{stats['highlights']}** menção sensível, sem ameaças sistêmicas iminentes.",
            f"Tudo tranquilo no front.\n\nVolume de anomalias sob controle (**{stats['highlights']}** críticos em **{stats['total']}** eventos). A inteligência coletada fala primariamente sobre **{top_tags_str}**.",
        ]

    missao = f"{saudacao}. {random.choice(mensagens)}"
    top_threats = top_tags_str

    return missao, resumo_executivo, top_threats


# ==============================================================
# COLETA E INSERÇÃO DE NOTÍCIAS
# ==============================================================

def fetch_news() -> list[dict]:
    hoje = now_br().date()
    yesterday = hoje - timedelta(days=1)
    items: list[dict] = []

    feeds = load_feeds()

    if not feeds:
        log.warning("Nenhum feed configurado. Encerrando coleta.")
        return []

    for feed in feeds:
        log.info(f"Buscando: {feed['name']}")

        try:
            parsed = feedparser.parse(feed["url"])

            if parsed.bozo:
                log.warning(f"Feed com possível erro de parsing: {feed['name']}")

            for entry in parsed.entries:
                pub = entry.get("published_parsed") or entry.get("updated_parsed")

                if pub and date(pub.tm_year, pub.tm_mon, pub.tm_mday) < yesterday:
                    continue

                title = entry.get("title", "")
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                url = entry.get("link", "")

                if not title or not url:
                    continue

                if not is_relevant(title, summary):
                    continue

                items.append(
                    {
                        "title": title,
                        "summary": summary[:400],
                        "url": url,
                        "source": feed["source"],
                        "categories": get_cats(title, summary),
                        "tags": get_tags(title, summary),
                        "date": hoje.isoformat(),
                        "themes": get_themes(title, summary, feed["source"]),
                        "signal_type": classify_signal_type(title, summary),
                    }
                )

        except Exception as error:
            log.warning(f"⚠️ Erro no feed {feed.get('name', 'unknown')}: {error}")
            continue

    log.info(f"Total relevante: {len(items)}")
    return items


def get_existing_url_map(notion: Client) -> dict[str, str]:
    url_map: dict[str, str] = {}
    cursor = None

    while True:
        params = {
            "data_source_id": NEWS_DB_ID,
            "page_size": 100,
        }

        if cursor:
            params["start_cursor"] = cursor

        resp = notion.data_sources.query(**params)

        for page in resp.get("results", []):
            url = page["properties"].get("URL", {}).get("url", "")
            if url:
                url_map[url] = page["id"]

        if not resp.get("has_more"):
            break

        cursor = resp["next_cursor"]

    return url_map


def insert_news(notion: Client, items: list[dict], existing_map: dict[str, str]) -> tuple[list[str], list[str]]:
    new_ids: list[str] = []
    reused_ids: list[str] = []

    for item in items:
        if item["url"] in existing_map:
            reused_ids.append(existing_map[item["url"]])
            continue

        try:
            page = notion.pages.create(
                parent={"data_source_id": NEWS_DB_ID},
                properties={
                    "Título": {"title": [{"text": {"content": item["title"][:200]}}]},
                    "Resumo": {"rich_text": notion_rich_text(item["summary"], limit=900)},
                    "URL": {"url": item["url"]},
                    "Fonte": {"select": {"name": item["source"]}},
                    "Categoria": {"multi_select": [{"name": c} for c in item["categories"]]},
                    "Tags": {"multi_select": [{"name": t} for t in item["tags"]]},
                    "Status": {"select": {"name": "Nova"}},
                    "Data": {"date": {"start": item["date"]}},
                    "Destaque": {"checkbox": False},
                    "Tema": {"multi_select": [{"name": t} for t in item["themes"]]},
                    "Tipo de Sinal": {"select": {"name": item["signal_type"]}},
                },
            )

            existing_map[item["url"]] = page["id"]
            new_ids.append(page["id"])
            log.info(f"🆕 {item['title'][:60]}")

        except Exception as error:
            log.error(f"Erro ao inserir '{item['title'][:40]}': {error}")

    return new_ids, reused_ids


def get_today_ids(notion: Client) -> list[str]:
    ids: list[str] = []
    cursor = None
    today = today_br()

    while True:
        params = {
            "data_source_id": NEWS_DB_ID,
            "page_size": 100,
            "filter": {
                "property": "Data",
                "date": {"equals": today},
            },
        }

        if cursor:
            params["start_cursor"] = cursor

        resp = notion.data_sources.query(**params)
        ids += [page["id"] for page in resp.get("results", [])]

        if not resp.get("has_more"):
            break

        cursor = resp["next_cursor"]

    return ids


# ==============================================================
# CARD BYTE
# ==============================================================

def upsert_byte_card(notion: Client, news_ids: list[str], stats: dict) -> None:
    today = today_br()
    cover_url = get_cover_by_level(stats["level"])

    resp = notion.data_sources.query(
        data_source_id=BYTE_DB_ID,
        filter={
            "property": "Data do Briefing",
            "date": {"equals": today},
        },
        page_size=1,
    )

    if resp.get("results"):
        ciclo = resp["results"][0]["properties"].get("🔁 Ciclo", {}).get("number", 0) or 0
        ciclo += 1
    else:
        ciclo = 1

    missao, resumo_executivo, top_threats = build_agent_message(stats)
    relations = [{"id": nid} for nid in news_ids]
    agora_iso = now_br().isoformat()
    terminal_text = build_terminal(stats)

    cores_alerta = {
        "🔴 CRÍTICO": "red",
        "🟠 ALTO": "orange",
        "🟡 MÉDIO": "yellow",
        "🟢 BAIXO": "green",
    }

    cor_hoje = cores_alerta.get(stats["level"], "default")
    top_themes_str = " • ".join(theme for theme, _ in stats.get("top_themes", [])[:3]) or "Geral"
    critical_url = (CRITICAL_VIEW_URL or "").strip()

    if not critical_url or not critical_url.startswith("http"):
        critical_link_text = {
            "text": {
                "content": "⚠️ Link não configurado",
            }
        }
    else:
        critical_link_text = {
            "text": {
                "content": f"{stats['highlights']} críticos",
                "link": {"url": critical_url},
            }
        }

    props = {
        "Agente": {"title": [{"text": {"content": "BYTE"}}]},
        "Missão do Dia": {"rich_text": formatar_notion(missao, cor_hoje)},
        "Resumo Executivo": {"rich_text": notion_rich_text(resumo_executivo)},
        "🚨 Critical Link": {"rich_text": [critical_link_text]},
        "Nível de Alerta": {"select": {"name": stats["level"]}},
        "Status do Agente": {"select": {"name": status_agent(stats["level"])}},
        "Data do Briefing": {"date": {"start": today}},
        "Última Atualização": {"date": {"start": agora_iso}},
        "⚡ Events": {"number": stats["total"]},
        "🚨 Critical": {"number": stats["highlights"]},
        "🧠 Top Threats": {"rich_text": notion_rich_text(top_threats)},
        "Terminal Raw": {"rich_text": notion_rich_text(terminal_text, limit=1800)},
        "🟢 Novas": {"number": stats["new_total"]},
        "🔁 Ciclo": {"number": ciclo},
        "🧭 Tema Dominante": {"rich_text": notion_rich_text(top_themes_str)},
        "🚨 Ameaças Reais": {"number": stats["signal_types"].get("🚨 Ameaça Real", 0)},
    }

    if relations:
        props["🗞️ Notícias Hoje"] = {"relation": relations}

    if resp.get("results"):
        page_id = resp["results"][0]["id"]
        notion.pages.update(
            page_id=page_id,
            properties=props,
            cover={
                "type": "external",
                "external": {"url": cover_url},
            },
        )
        log.info("✅ Card BYTE atualizado")
    else:
        notion.pages.create(
            parent={"data_source_id": BYTE_DB_ID},
            cover={
                "type": "external",
                "external": {"url": cover_url},
            },
            icon={"type": "emoji", "emoji": "🤖"},
            properties=props,
        )
        log.info("✅ Card BYTE criado")


# ==============================================================
# EXECUÇÃO PRINCIPAL
# ==============================================================

def build_stats(items: list[dict], new_ids: list[str], reused_ids: list[str]) -> dict:
    cat_counter = Counter()
    tag_counter = Counter()
    source_counter = Counter()
    theme_counter = Counter()
    signal_counter = Counter()

    for item in items:
        for cat in item["categories"]:
            cat_counter[cat] += 1
        for tag in item["tags"]:
            tag_counter[tag] += 1
        for theme in item["themes"]:
            theme_counter[theme] += 1

        source_counter[item["source"]] += 1
        signal_counter[item["signal_type"]] += 1

    critical_tags = {"Zero-day", "Critical Infrastructure", "Ransomware", "APT"}

    highlights = sum(
        1
        for item in items
        if (
            item.get("signal_type") == "🚨 Ameaça Real"
            or any(tag in critical_tags for tag in item["tags"])
        )
    )

    total_feed = len(items)
    total_new = len(new_ids)
    total_reused = len(reused_ids)
    total_cycle = total_new + total_reused

    return {
        "total": total_feed,
        "feed_total": total_feed,
        "new_total": total_new,
        "reused_total": total_reused,
        "cycle_total": total_cycle,
        "highlights": highlights,
        "level": threat_level(highlights),
        "top_tags": tag_counter.most_common(5),
        "top_cats": cat_counter.most_common(5),
        "by_source": dict(source_counter),
        "top_themes": theme_counter.most_common(5),
        "signal_types": dict(signal_counter),
    }


def main() -> None:
    log.info("=" * 60)
    log.info("  🤖 BYTE CyberWatch v2 — Ciclo diário iniciado")
    log.info("=" * 60)

    if not validate_environment():
        return

    notion = Client(auth=NOTION_TOKEN)

    items = fetch_news()
    existing_map = get_existing_url_map(notion)
    new_ids, reused_ids = insert_news(notion, items, existing_map)

    log.info(f"📥 {len(new_ids)} novas notícias inseridas")

    today_ids = get_today_ids(notion)
    log.info(f"📋 Total notícias de hoje: {len(today_ids)}")

    stats = build_stats(items, new_ids, reused_ids)

    log.info(f"🔎 Feed relevante: {stats['feed_total']}")
    log.info(f"🆕 Novas inseridas: {stats['new_total']}")
    log.info(f"♻️ Reutilizadas: {stats['reused_total']}")
    log.info(f"📦 Total do ciclo: {stats['cycle_total']}")
    log.info(f"🚦 Nível de alerta: {stats['level']}")

    cycle_ids = new_ids + reused_ids
    upsert_byte_card(notion, cycle_ids, stats)

    log.info("=" * 60)
    log.info(
        f"  ✅ Concluído! {len(new_ids)} novas · {len(today_ids)} hoje · Nível: {stats['level']}"
    )
    log.info("=" * 60)


if __name__ == "__main__":
    main()
