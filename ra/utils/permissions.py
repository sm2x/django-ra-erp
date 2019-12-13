from __future__ import unicode_literals

from ra.reporting.registry import report_registry

from django.apps import apps as global_apps
from django.contrib.contenttypes.management import create_contenttypes
from django.db import DEFAULT_DB_ALIAS, router


def _get_all_permissions(report):
    """
    Return (codename, name) for all permissions in the given opts.
    """
    return [*_get_builtin_permissions(report)]


def _get_builtin_permissions(report):
    """
    Return (codename, name) for all autogenerated permissions.
    By default, this is ('add', 'change', 'delete', 'view')
    """
    default_permissions = ['print', 'view']
    perms = []
    for action in default_permissions:
        permission_name = '%s_%s' % (action, report.get_report_slug())
        perms.append((
            permission_name,
            'Can %s %s' % (action, report.report_title)
        ))
    return perms


def create_report_permissions(app_config, verbosity=2, interactive=True, using=DEFAULT_DB_ALIAS, apps=global_apps,
                              **kwargs):
    """
    Copied from django create permissions for model, edited to create view and print for reports
    Reports permissions are created in the database similar to django's

    app.print_clientbalances (ClientBalances is the report slug (defaulting to report class name), Content Type is the
    base model content_type

    :param app_config:
    :param verbosity:
    :param interactive:
    :param using:
    :param apps:
    :param kwargs:
    :return:
    """

    if not app_config.models_module:
        return

    # Ensure that contenttypes are created for this app. Needed if
    # 'django.contrib.auth' is in INSTALLED_APPS before
    # 'django.contrib.contenttypes'.
    create_contenttypes(app_config, verbosity=verbosity, interactive=interactive, using=using, apps=apps, **kwargs)

    app_label = app_config.label
    try:
        app_config = apps.get_app_config(app_label)
        ContentType = apps.get_model('contenttypes', 'ContentType')
        Permission = apps.get_model('auth', 'Permission')
    except LookupError:
        return

    if not router.allow_migrate_model(using, Permission):
        return

    # This will hold the permissions we're looking for as
    # (content_type, (codename, name))
    all_reports = report_registry.get_all_reports()
    searched_perms = []
    # The codenames and ctypes that should exist.
    ctypes = set()
    for report in all_reports:
        # for klass in report_registry.get_base_models():
        # Force looking up the content types in the current database
        # before creating foreign keys to them.
        klass = report.base_model
        ctype = ContentType.objects.db_manager(using).get_for_model(klass, for_concrete_model=False)

        ctypes.add(ctype)
        for perm in _get_all_permissions(report):
            searched_perms.append((ctype, perm))

    # Find all the Permissions that have a content_type for a model we're
    # looking for.  We don't need to check for codenames since we already have
    # a list of the ones we're going to create.
    all_perms = set(Permission.objects.using(using).filter(
        content_type__in=ctypes,
    ).values_list(
        "content_type", "codename"
    ))

    perms = [
        Permission(codename=codename, name=name, content_type=ct)
        for ct, (codename, name) in searched_perms
        if (ct.pk, codename) not in all_perms
    ]
    Permission.objects.using(using).bulk_create(perms)
    if verbosity >= 2:
        for perm in perms:
            print("Adding permission '%s'" % perm)


def has_report_permission_permission(request, namespace, slug):
    user = request.user
    if user.is_superuser:
        return True
    else:
        return '%s.%s_print' % (namespace, slug) in request.session.get('user_reports', '')