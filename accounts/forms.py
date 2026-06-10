from allauth.account.forms import LoginForm


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["login"].label = "ユーザー名"
        self.fields["login"].widget.attrs["placeholder"] = "ユーザー名"