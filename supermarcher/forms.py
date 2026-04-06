from django import forms
from .models import ThemeMagasin, Utilisateur
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

# users/forms.py
from django import forms
from .models import Utilisateur
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import Utilisateur
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import Utilisateur


class UtilisateurForm(forms.ModelForm):

    password = forms.CharField(widget=forms.PasswordInput, required=False)
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = Utilisateur
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "telephone",
        ]

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.get("instance", None)
        super().__init__(*args, **kwargs)

    # 🔐 USERNAME (par magasin + exclude self en edit)
    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        qs = Utilisateur.objects.filter(username=username)

        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("Username déjà utilisé")

        if len(username) < 3:
            raise ValidationError("Username trop court")

        return username

    # 🔐 EMAIL (par magasin + exclude self)
    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        qs = Utilisateur.objects.filter(email=email)

        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("Email déjà utilisé")

        return email

    # 🔐 PASSWORD CHECK
    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        # ✔ seulement si l'utilisateur veut changer mot de passe
        if password or password_confirm:

            if password != password_confirm:
                self.add_error("password_confirm", "Les mots de passe ne correspondent pas")

            if password:
                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error("password", e)

        return cleaned_data

    # 🔐 SAVE SECURISÉ
    def save(self, commit=True):
        user = super().save(commit=False)

        password = self.cleaned_data.get("password")

        if password:
            user.set_password(password)

        if commit:
            user.save()

        return user
    
from django import forms
from django.core.cache import cache
import time

class ConnexionForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()

        username = cleaned_data.get("username")
        if not username:
            return cleaned_data

        key = f"login_attempts_{username}"
        data = cache.get(key, {"count": 0, "block_until": 0})

        now = time.time()

        # ⛔ si encore bloqué
        if data["block_until"] > now:
            remaining = int(data["block_until"] - now)
            raise forms.ValidationError(
                f"Trop de tentatives. Réessayez dans {remaining} secondes."
            )

        return cleaned_data

    def register_failed_attempt(self, username):
        key = f"login_attempts_{username}"
        data = cache.get(key, {"count": 0, "block_until": 0})

        data["count"] += 1

        # 🔥 backoff progressif
        if data["count"] <= 3:
            delay = 0
        else:
            # 1 min puis +2 min, +4 min...
            delay = 60 * (2 ** (data["count"] - 4))

        if delay > 0:
            data["block_until"] = time.time() + delay

        cache.set(key, data, timeout=60 * 60)  # 1h mémoire max
    
from django.core.exceptions import ValidationError
from .models import Magasin, Utilisateur
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
import re

class CreationMagasinForm(forms.ModelForm):

    gerant_username = forms.CharField(
        label="Nom utilisateur gérant",
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Nom utilisateur'})
    )

    gerant_email = forms.EmailField(
        label="Email gérant",
        widget=forms.EmailInput(attrs={'placeholder': 'Email'})
    )

    gerant_password = forms.CharField(
        label="Mot de passe gérant",
        widget=forms.PasswordInput(attrs={'placeholder': 'Mot de passe'})
    )

    gerant_password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirmer le mot de passe'})
    )

    class Meta:
        model = Magasin
        fields = [
            "nom",
            "adresse",
            "ville",
            "pays",
            "telephone",
            "email"
        ]

    # 🔐 USERNAME sécurisé
    def clean_gerant_username(self):
        username = self.cleaned_data["gerant_username"].strip()

        if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
            raise ValidationError(
                "Seulement lettres, chiffres, ., _, - autorisés"
            )

        if len(username) < 3:
            raise ValidationError("Nom utilisateur trop court")

        from .models import Utilisateur
        if Utilisateur.objects.filter(username=username).exists():
            raise ValidationError("Nom utilisateur déjà utilisé")

        return username

    # 🔐 EMAIL sécurisé
    def clean_gerant_email(self):
        email = self.cleaned_data["gerant_email"].strip().lower()

        from .models import Utilisateur
        if Utilisateur.objects.filter(email=email).exists():
            raise ValidationError("Email déjà utilisé")

        return email

    # 🔐 TÉLÉPHONE sécurisé
    def clean_telephone(self):
        telephone = self.cleaned_data.get("telephone", "").strip()

        if telephone and not re.match(r"^\+?[0-9\s\-]{8,20}$", telephone):
            raise ValidationError("Numéro de téléphone invalide")

        return telephone

    # 🔐 VALIDATION GLOBALE
    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("gerant_password")
        password2 = cleaned_data.get("gerant_password2")

        # ✔️ correspondance
        if password and password2:
            if password != password2:
                self.add_error("gerant_password2", "Les mots de passe ne correspondent pas")

        # ✔️ validation Django (IMPORTANT)
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                self.add_error("gerant_password", e)

        return cleaned_data

class ModifierMagasinForm(forms.ModelForm):
    class Meta:
        model = Magasin
        fields = [
            "nom",
            "adresse",
            "ville",
            "pays",
            "telephone",
            "email"
        ]

    def clean_telephone(self):
        import re
        telephone = self.cleaned_data.get("telephone", "").strip()

        if telephone and not re.match(r"^\+?[0-9\s\-]{8,20}$", telephone):
            raise forms.ValidationError("Numéro invalide")

        return telephone
    
# parametre magasin
class MagasinForm(forms.ModelForm):
    class Meta:
        model = Magasin
        fields = ['nom', 'adresse', 'ville', 'pays', 'telephone', 'email', 'devise']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'adresse': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white', 'rows': 2}),
            'ville': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'pays': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'telephone': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'devise': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
        }

from .models import ThemeMagasin

class ThemeMagasinForm(forms.ModelForm):

    logo = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            "class": "file-input file-input-bordered"
        })
    )

    class Meta:
        model = ThemeMagasin
        fields = ["couleur_principale", "logo"]

        widgets = {
            "couleur_principale": forms.TextInput(
                attrs={
                    "type": "color",
                    "class": "w-20 h-12 rounded-lg border cursor-pointer"
                }
            ),
        }
        
        
from django import forms
from .models import Produit, Categorie

from django import forms
from .models import Produit
from django import forms
from .models import Produit
from django import forms
from django.core.exceptions import ValidationError
from .models import Produit


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = [
            'categorie', 'nom', 'code_barre', 'sku', 'description',
            'prix_achat', 'prix_vente', 'taux_tva', 'quantite_stock',
            'seuil_alerte', 'actif', 'date_fabrication', 'date_expiration'
        ]
        widgets = {
            'categorie': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'nom': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'code_barre': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'sku': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white',
                'rows': 3
            }),
            'prix_achat': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'prix_vente': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'taux_tva': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'quantite_stock': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg bg-gray-100 dark:bg-gray-800 dark:text-white',
                'readonly': 'readonly',
                'placeholder': 'Géré automatiquement'
            }),
            'seuil_alerte': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'actif': forms.CheckboxInput(attrs={
                'class': 'h-5 w-5 text-green-600'
            }),
            'date_fabrication': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'date_expiration': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
        }

    from django.core.exceptions import ValidationError

    def clean(self):
        cleaned_data = super().clean()

        nom = cleaned_data.get("nom")
        sku = cleaned_data.get("sku")
        code_barre = cleaned_data.get("code_barre")
        magasin = getattr(self.instance, "magasin", None)

        if nom and sku and code_barre and magasin:

            qs = Produit.objects.filter(
                nom=nom,
                sku=sku,
                code_barre=code_barre,
                magasin=magasin
            )

            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    "Ce produit existe déjà. Vérifiez le nom, le SKU ou le code-barres."
                )

        return cleaned_data
    
    
from django import forms
from .models import Categorie
from django.core.exceptions import ValidationError
from django import forms
from django.core.exceptions import ValidationError
from .models import Categorie


class CategorieForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.magasin = kwargs.pop('magasin', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Categorie
        fields = ['nom', 'description']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white',
                'rows': 3
            }),
        }

    from django.core.exceptions import ValidationError

    def clean(self):
        cleaned_data = super().clean()

        nom = cleaned_data.get("nom")
        description = cleaned_data.get("description")

        if nom and self.magasin:
            qs = Categorie.objects.filter(
                nom__iexact=nom,
                magasin=self.magasin
            )

            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(" ")

        if description and self.magasin:
            qs = Categorie.objects.filter(
                description__iexact=description,
                magasin=self.magasin
            )

            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(" ")

        return cleaned_data
    
from django import forms
from .models import Fournisseur
from django import forms
from django.core.exceptions import ValidationError
from .models import Fournisseur


class FournisseurForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.magasin = kwargs.pop('magasin', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Fournisseur
        fields = ['nom', 'prenom', 'telephone', 'email', 'adresse']

        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'prenom': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'
            }),
            'adresse': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white',
                'rows': 3
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        nom = cleaned_data.get("nom")
        prenom = cleaned_data.get("prenom")
        telephone = cleaned_data.get("telephone")
        email = cleaned_data.get("email")

        if not self.magasin:
            return cleaned_data

        qs = Fournisseur.objects.filter(magasin=self.magasin)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        # 🔥 Doublon téléphone
        if telephone and qs.filter(telephone=telephone).exists():
            raise ValidationError(" ")

        # 🔥 Doublon email
        if email and qs.filter(email__iexact=email).exists():
            raise ValidationError(" ")

        # 🔥 Doublon nom + prénom
        if nom and prenom and qs.filter(
            nom__iexact=nom,
            prenom__iexact=prenom
        ).exists():
            raise ValidationError(" ")

        return cleaned_data
        
from django import forms
from django.forms import inlineformset_factory
from .models import Achat, LigneAchat

class AchatForm(forms.ModelForm):
    class Meta:
        model = Achat
        fields = ['fournisseur', 'numero_facture']
        widgets = {
            'fournisseur': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'numero_facture': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
        }

class LigneAchatForm(forms.ModelForm):
    class Meta:
        model = LigneAchat
        fields = ['produit', 'quantite', 'prix_unitaire']
        widgets = {
            'produit': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'quantite': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg dark:bg-gray-800 dark:text-white'}),
        }


LigneAchatFormSet = inlineformset_factory(
    Achat,
    LigneAchat,
    form=LigneAchatForm,
    extra=1,
    can_delete=True
)


from django import forms
from django.forms import inlineformset_factory
from .models import Vente, LigneVente


# ================================
# FORMULAIRE VENTE
# ================================
class VenteForm(forms.ModelForm):
    remise = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,  # <-- ici
        initial=0
    )

    class Meta:
        model = Vente
        fields = [
            "client_nom",
            "mode_paiement",
            "remise",
        ]
        widgets = {
            "client_nom": forms.TextInput(attrs={
                "class": "w-full border rounded-lg p-2"
            }),
            "mode_paiement": forms.Select(attrs={
                "class": "w-full border rounded-lg p-2"
            }),
            "remise": forms.NumberInput(attrs={
                "class": "w-full border rounded-lg p-2",
                "step": "0.01"
            }),
        }

# ================================
# FORMULAIRE LIGNE VENTE
# ================================
class LigneVenteForm(forms.ModelForm):
    class Meta:
        model = LigneVente
        fields = [
            "produit",
            "quantite",
            "prix_unitaire",
        ]
        widgets = {
            "produit": forms.Select(attrs={
                "class": "w-full border rounded-lg p-2"
            }),
            "quantite": forms.NumberInput(attrs={
                "class": "w-full border rounded-lg p-2"
            }),
            "prix_unitaire": forms.NumberInput(attrs={
                "class": "w-full border rounded-lg p-2",
                "step": "0.01"
            }),
        }


# ================================
# FORMSET LIGNES DE VENTE
# ================================
LigneVenteFormSet = inlineformset_factory(
    Vente,
    LigneVente,
    form=LigneVenteForm,
    extra=1,
    can_delete=True
)