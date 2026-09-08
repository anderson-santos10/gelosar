"""Política de upload de documentos de equipamento (ALTO-007).

Allowlist (extensão em minúsculas + assinatura no início do arquivo):

* .pdf  — começa com %PDF
* .png  — assinatura PNG
* .jpg / .jpeg — começa com FF D8 FF
* .docx / .xlsx — arquivo ZIP (PK); formatos Office com macro (.docm, .xlsm, …) são recusados

Extensão e Content-Type do navegador NÃO bastam. HTML/SVG/JS/XML ativos são bloqueados
pela allowlist. Conteúdo HTML enviado como .pdf é rejeitado pela assinatura.

O download na aplicação usa Content-Disposition: attachment e
Content-Type: application/octet-stream para o arquivo não ser interpretado
como página no domínio da aplicação.
"""

from pathlib import Path

from django.core.exceptions import ValidationError

EXTENSOES_PERMITIDAS = frozenset({
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".docx",
    ".xlsx",
})

EXTENSOES_BLOQUEADAS = frozenset({
    ".html",
    ".htm",
    ".shtml",
    ".xhtml",
    ".svg",
    ".js",
    ".mjs",
    ".xml",
    ".xsl",
    ".xslt",
    ".mhtml",
    ".mht",
    ".hta",
    ".docm",
    ".xlsm",
    ".pptm",
    ".dotm",
    ".xltm",
    ".ppam",
})

ASSINATURAS = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

MENSAGEM_TIPO_NAO_PERMITIDO = (
    "Tipo de arquivo não permitido. Envie PDF, PNG, JPEG, DOCX ou XLSX."
)
MENSAGEM_CONTEUDO_INVALIDO = (
    "O conteúdo do arquivo não corresponde ao tipo informado."
)


def extensao_arquivo(nome):
    return Path(nome or "").suffix.lower()


def _ler_inicio(arquivo, tamanho=16):
    posicao = None
    if hasattr(arquivo, "tell"):
        try:
            posicao = arquivo.tell()
        except Exception:
            posicao = None
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    dados = arquivo.read(tamanho) or b""
    if hasattr(arquivo, "seek"):
        if posicao is not None:
            arquivo.seek(posicao)
        else:
            arquivo.seek(0)
    if isinstance(dados, str):
        dados = dados.encode("latin-1", errors="ignore")
    return dados


def _assinatura_valida(extensao, inicio):
    esperadas = ASSINATURAS.get(extensao, ())
    if not esperadas or not inicio:
        return False
    if extensao == ".pdf":
        amostra = inicio.lstrip()
        return any(amostra.startswith(sig) for sig in esperadas)
    return any(inicio.startswith(sig) for sig in esperadas)


def validar_arquivo_documento(arquivo):
    nome = getattr(arquivo, "name", "") or ""
    extensao = extensao_arquivo(nome)

    if extensao in EXTENSOES_BLOQUEADAS or extensao not in EXTENSOES_PERMITIDAS:
        raise ValidationError(MENSAGEM_TIPO_NAO_PERMITIDO)

    inicio = _ler_inicio(arquivo)
    if not _assinatura_valida(extensao, inicio):
        raise ValidationError(MENSAGEM_CONTEUDO_INVALIDO)
