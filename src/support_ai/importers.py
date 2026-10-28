"""Turn local files into reviewable Markdown. Never resolve URLs or execute content."""

import json
from pathlib import PurePosixPath

from support_ai.guide import GuideError, slug, validate_content


def import_document(filename: str, content: str, project: str, area: str) -> tuple[str, str]:
    if not filename or "/" in filename or "\\" in filename or len(filename) > 160:
        raise GuideError("Selecciona un archivo local con un nombre válido.")
    validate_content(content)
    suffix = PurePosixPath(filename).suffix.lower()
    prefix = f"Proyecto: {project or 'General'}\nÁrea: {area or 'General'}\nFuente: {filename}\n\n"
    if suffix == ".md":
        markdown = prefix + content
    elif suffix == ".txt":
        markdown = f"# {PurePosixPath(filename).stem}\n\n{prefix}{content}"
    elif suffix == ".json":
        try:
            source = json.loads(content)
        except ValueError as exc:
            raise GuideError("El JSON no es válido.") from exc
        if not isinstance(source, dict):
            raise GuideError("El JSON debe contener un objeto OpenAPI, Postman o documentación.")
        if "openapi" in source or "swagger" in source:
            info = source.get("info", {})
            if not all(
                isinstance(source.get(key, {}), dict) for key in ("info", "components", "paths")
            ):
                raise GuideError("OpenAPI requiere objetos info, components y paths válidos.")
            lines = [
                f"# {info.get('title', filename)}",
                "",
                prefix,
                str(info.get("description", "")),
                "",
                "## Servidores",
                "",
                json.dumps(
                    source.get(
                        "servers",
                        {
                            key: source[key]
                            for key in (
                                "host",
                                "basePath",
                                "schemes",
                            )
                            if key in source
                        },
                    ),
                    ensure_ascii=False,
                ),
                "",
                "## Seguridad declarada",
                "",
                json.dumps(
                    {
                        "security": source.get("security", []),
                        "schemes": source.get("components", {}).get(
                            "securitySchemes", source.get("securityDefinitions", {})
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "",
            ]
            for path, operations in source.get("paths", {}).items():
                if not isinstance(operations, dict):
                    continue
                for method, operation in operations.items():
                    if method.lower() not in (
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                        "head",
                        "options",
                    ):
                        continue
                    if not isinstance(operation, dict):
                        raise GuideError("Cada operación OpenAPI debe ser un objeto JSON.")
                    lines.extend(
                        [
                            f"## {method.upper()} {path}",
                            "",
                            str(operation.get("summary", "")),
                            str(operation.get("description", "")),
                            "",
                            "```json",
                            json.dumps(operation, ensure_ascii=False, indent=2),
                            "```",
                            "",
                        ]
                    )
            markdown = "\n".join(lines)
        else:
            kind = "Colección Postman" if "item" in source else "Documento JSON"
            markdown = (
                f"# {kind}: {filename}\n\n{prefix}"
                f"```json\n{json.dumps(source, ensure_ascii=False, indent=2)}\n```\n"
            )
    else:
        raise GuideError("Por ahora puedes importar Markdown, TXT y JSON (OpenAPI o Postman).")
    validate_content(markdown)
    path = (
        f"projects/{slug(project)}/{slug(area)}/importados/{slug(PurePosixPath(filename).stem)}.md"
    )
    return path, markdown
