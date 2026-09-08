from django.contrib import admin
from django.db.models import Sum
from django.urls import NoReverseMatch, reverse

from core.periodo import dia_local_atual, intervalo_dia_local


class GelosarAdminSite(admin.AdminSite):
    site_header = "GELOSAR"
    site_title = "Administração GELOSAR"
    index_title = "Dashboard administrativo"
    site_url = "/dashboard/"
    enable_nav_sidebar = True

    def each_context(self, request):
        context = super().each_context(request)
        context["gs_nav_groups"] = self._nav_groups(request)
        try:
            context["gs_sistema_url"] = reverse("dashboard")
        except NoReverseMatch:
            context["gs_sistema_url"] = self.site_url
        return context

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["gs_dashboard_cards"] = self._dashboard_cards(request)
        extra_context["gs_dashboard_kpis"] = self._dashboard_kpis(request)
        return super().index(request, extra_context)

    def _nav_groups(self, request):
        user = request.user
        path = request.path

        def item(name, label, perm, icon):
            if perm and not user.has_perm(perm):
                return None
            try:
                url = reverse(name)
            except NoReverseMatch:
                return None
            current = path == url or (
                name != "admin:index" and path.startswith(url)
            )
            return {
                "url": url,
                "label": label,
                "icon": icon,
                "current": current,
            }

        groups = [
            (
                "Dashboard",
                [
                    item("admin:index", "Dashboard", None, "bi-grid-1x2"),
                ],
            ),
            (
                "Comercial",
                [
                    item(
                        "admin:clientes_cliente_changelist",
                        "Clientes",
                        "clientes.view_cliente",
                        "bi-people",
                    ),
                    item(
                        "admin:vendas_venda_changelist",
                        "Vendas",
                        "vendas.view_venda",
                        "bi-cart3",
                    ),
                ],
            ),
            (
                "Operação",
                [
                    item(
                        "admin:producao_producao_changelist",
                        "Produção",
                        "producao.view_producao",
                        "bi-lightning-charge",
                    ),
                    item(
                        "admin:produtos_produto_changelist",
                        "Produtos",
                        "produtos.view_produto",
                        "bi-box",
                    ),
                    item(
                        "admin:insumos_insumo_changelist",
                        "Insumos",
                        "insumos.view_insumo",
                        "bi-droplet",
                    ),
                ],
            ),
            (
                "Equipamentos",
                [
                    item(
                        "admin:equipamentos_equipamento_changelist",
                        "Equipamentos",
                        "equipamentos.view_equipamento",
                        "bi-tools",
                    ),
                    item(
                        "admin:equipamentos_contratocomodato_changelist",
                        "Contratos de comodato",
                        "equipamentos.view_contratocomodato",
                        "bi-file-earmark-check",
                    ),
                ],
            ),
            (
                "Sistema",
                [
                    item(
                        "admin:auth_user_changelist",
                        "Usuários",
                        "auth.view_user",
                        "bi-person-badge",
                    ),
                    item(
                        "admin:auth_group_changelist",
                        "Grupos",
                        "auth.view_group",
                        "bi-shield-check",
                    ),
                ],
            ),
        ]
        result = []
        for title, items in groups:
            visible = [entry for entry in items if entry]
            if visible:
                result.append({"title": title, "items": visible})
        return result

    def _dashboard_cards(self, request):
        user = request.user
        cards = []

        def add(label, perm, queryset, url_name, icon):
            if perm and not user.has_perm(perm):
                return
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                url = ""
            cards.append(
                {
                    "label": label,
                    "value": queryset.count(),
                    "url": url,
                    "icon": icon,
                }
            )

        from clientes.models import Cliente
        from equipamentos.models import ContratoComodato, Equipamento
        from insumos.models import Insumo
        from producao.models import Producao
        from produtos.models import Produto
        from vendas.models import Venda

        add(
            "Clientes",
            "clientes.view_cliente",
            Cliente.objects.all(),
            "admin:clientes_cliente_changelist",
            "bi-people",
        )
        add(
            "Equipamentos",
            "equipamentos.view_equipamento",
            Equipamento.objects.all(),
            "admin:equipamentos_equipamento_changelist",
            "bi-tools",
        )
        add(
            "Contratos de comodato",
            "equipamentos.view_contratocomodato",
            ContratoComodato.objects.all(),
            "admin:equipamentos_contratocomodato_changelist",
            "bi-file-earmark-check",
        )
        add(
            "Produtos",
            "produtos.view_produto",
            Produto.objects.all(),
            "admin:produtos_produto_changelist",
            "bi-box",
        )
        add(
            "Insumos",
            "insumos.view_insumo",
            Insumo.objects.all(),
            "admin:insumos_insumo_changelist",
            "bi-droplet",
        )
        add(
            "Produções",
            "producao.view_producao",
            Producao.objects.all(),
            "admin:producao_producao_changelist",
            "bi-lightning-charge",
        )
        add(
            "Vendas",
            "vendas.view_venda",
            Venda.objects.all(),
            "admin:vendas_venda_changelist",
            "bi-cart3",
        )
        return cards

    def _dashboard_kpis(self, request):
        user = request.user
        kpis = []
        hoje = dia_local_atual()
        inicio_hoje, fim_hoje = intervalo_dia_local(hoje)
        inicio_mes = hoje.replace(day=1)

        if user.has_perm("estoque.view_movimentacaoproduto"):
            from estoque.services import calcular_estoques_produto_por_peso

            saldos = calcular_estoques_produto_por_peso(3, 5)
            kpis.append(
                {"label": "Estoque gelo 5kg", "value": saldos[5], "hint": "sacos"}
            )
            kpis.append(
                {"label": "Estoque gelo 3kg", "value": saldos[3], "hint": "sacos"}
            )

        if user.has_perm("equipamentos.view_contratocomodato"):
            from equipamentos.models import ContratoComodato

            kpis.append(
                {
                    "label": "Comodatos ativos",
                    "value": ContratoComodato.objects.filter(status="ativo").count(),
                    "hint": "contratos",
                }
            )

        if user.has_perm("producao.view_producao"):
            from producao.models import Producao

            total = (
                Producao.objects.filter(
                    data_hora__gte=inicio_hoje,
                    data_hora__lt=fim_hoje,
                ).aggregate(total=Sum("quantidade"))["total"]
                or 0
            )
            kpis.append(
                {"label": "Produção do dia", "value": total, "hint": "unidades"}
            )

        if user.has_perm("vendas.view_venda"):
            from vendas.models import Venda

            kpis.append(
                {
                    "label": "Vendas do mês",
                    "value": Venda.objects.filter(data__gte=inicio_mes).count(),
                    "hint": inicio_mes.strftime("%m/%Y"),
                }
            )
        return kpis
