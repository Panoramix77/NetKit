with open("ROADMAP.md", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace(
    "### 1. Escáner de Puertos (Port Scanner)",
    "### 1. Escáner de Puertos (Port Scanner) [COMPLETADO]"
)

with open("ROADMAP.md", "w", encoding="utf-8") as f:
    f.write(text)
