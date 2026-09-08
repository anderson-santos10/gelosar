def atribuir_criado_por(instance, user):
    """Define o criador apenas na primeira atribuição. Não inventa usuário."""
    if getattr(instance, "criado_por_id", None):
        return instance
    if user is None or not getattr(user, "is_authenticated", False):
        return instance
    instance.criado_por = user
    return instance
