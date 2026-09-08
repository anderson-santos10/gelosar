from django.contrib.admin.apps import AdminConfig


class GelosarAdminConfig(AdminConfig):
    default_site = "core.admin_site.GelosarAdminSite"
