from allauth.account.forms import LoginForm
from django import forms

from .menu_registry import (
    ALL_MENU_KEYS,
    MENU_FEATURES,
    MENU_GROUPS,
    MENU_BY_KEY,
)
from .models import UserAccessProfile


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["login"].label = "ユーザー名"
        self.fields["login"].widget.attrs["placeholder"] = "ユーザー名"


def _menu_group_field_names():
    names = []
    for group_id, _ in MENU_GROUPS:
        keys = tuple(
            feature.key
            for feature in MENU_FEATURES
            if feature.group == group_id
        )
        if keys:
            names.append(f"menu_group_{group_id}")
    return tuple(names)


MENU_GROUP_FIELD_NAMES = _menu_group_field_names()


def _build_menu_group_field(group_id, group_label):
    keys = tuple(
        feature.key
        for feature in MENU_FEATURES
        if feature.group == group_id
    )
    return forms.MultipleChoiceField(
        choices=[(k, MENU_BY_KEY[k].label) for k in keys],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=group_label,
    )


def _user_access_form_init(self, *args, **kwargs):
    forms.ModelForm.__init__(self, *args, **kwargs)

    enabled = set()
    if self.instance.pk and self.instance.menu_permissions is not None:
        enabled = set(self.instance.menu_permissions)
        self.fields["allow_all_menus"].initial = False
    elif self.instance.pk:
        enabled = set(ALL_MENU_KEYS)
        self.fields["allow_all_menus"].initial = True
    else:
        enabled = set(ALL_MENU_KEYS)

    for group_id, _ in MENU_GROUPS:
        field_name = f"menu_group_{group_id}"
        if field_name not in self.fields:
            continue
        keys = tuple(
            feature.key
            for feature in MENU_FEATURES
            if feature.group == group_id
        )
        self.fields[field_name].initial = [k for k in keys if k in enabled]


def _user_access_form_save(self, commit=True):
    instance = forms.ModelForm.save(self, commit=False)

    if self.cleaned_data.get("allow_all_menus"):
        instance.menu_permissions = None
    else:
        selected = []
        for field_name in MENU_GROUP_FIELD_NAMES:
            if field_name in self.cleaned_data:
                selected.extend(self.cleaned_data[field_name])
        instance.menu_permissions = sorted(set(selected))

    if commit:
        instance.save()
    return instance


def _build_user_access_profile_form(class_name, meta_fields):
    form_attrs = {
        "allow_all_menus": forms.BooleanField(
            required=False,
            initial=True,
            label="全メニューを許可（従来どおり）",
            help_text="オフにすると、下で選択した画面のみ閲覧できます。",
        ),
        "__init__": _user_access_form_init,
        "save": _user_access_form_save,
        "Meta": type(
            "Meta",
            (),
            {
                "model": UserAccessProfile,
                "fields": meta_fields,
            },
        ),
    }

    for group_id, group_label in MENU_GROUPS:
        keys = tuple(
            feature.key
            for feature in MENU_FEATURES
            if feature.group == group_id
        )
        if keys:
            form_attrs[f"menu_group_{group_id}"] = _build_menu_group_field(
                group_id,
                group_label,
            )

    return type(class_name, (forms.ModelForm,), form_attrs)


UserAccessProfileAdminForm = _build_user_access_profile_form(
    "UserAccessProfileAdminForm",
    (
        "user",
        "allow_all_menus",
        *MENU_GROUP_FIELD_NAMES,
        "can_create",
        "can_update",
        "can_delete",
        "can_execute",
        "can_export",
    ),
)

UserAccessProfileInlineForm = _build_user_access_profile_form(
    "UserAccessProfileInlineForm",
    (
        "allow_all_menus",
        *MENU_GROUP_FIELD_NAMES,
        "can_create",
        "can_update",
        "can_delete",
        "can_execute",
        "can_export",
    ),
)
