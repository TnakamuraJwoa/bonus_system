from allauth.account.forms import SignupForm, LoginForm
from django import forms
from .models import CustomUser

class CustomSignupForm(SignupForm):
    gender = forms.ChoiceField(choices=CustomUser.GENDER, label='アカウントタイプ')
    my_username = forms.CharField(max_length=50, label='ユーザー名')

    class Meta:
        model = CustomUser

    def save(self, *args, **kwargs):
        # データベースにユーザーを保存する
        user = super(CustomSignupForm, self).save(*args, **kwargs)
        # カスタムフィールドの値を設定する
        user.gender = self.cleaned_data['gender']
        my_username = self.cleaned_data.get('my_username')
        if my_username:
            # my_username フィールドが存在する場合の処理
            user.username = my_username
        user.save()
        return user



class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['login'].widget.attrs['placeholder'] = 'ユーザー'