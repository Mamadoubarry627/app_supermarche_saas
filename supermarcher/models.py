from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
#supermarcher

# ================================
# UTILISATEUR PERSONNALISÉ
# ================================

from django.contrib.auth.models import AbstractUser, BaseUserManager

class UtilisateurManager(BaseUserManager):

    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email obligatoire")

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPERADMIN')

        return self.create_user(username, email, password, **extra_fields)

class Utilisateur(AbstractUser):
    ROLE_CHOICES = (
        ('SUPERADMIN', 'Super Admin'),
        ('GERANT', 'Gérant'),
        ('CAISSIER', 'Caissier'),
    )

    email = models.EmailField(unique=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='CAISSIER')
    magasin = models.ForeignKey('Magasin', on_delete=models.CASCADE, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    objects = UtilisateurManager()

    def save(self, *args, **kwargs):

        # 🔒 Sécurité automatique
        if self.role == 'SUPERADMIN':
            self.is_staff = True
            self.is_superuser = True

        elif self.role == 'GERANT':
            self.is_staff = True
            self.is_superuser = False

        elif self.role == 'CAISSIER':
            self.is_staff = False
            self.is_superuser = False

        super().save(*args, **kwargs)
    

    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['magasin']),
        ]

    def __str__(self):
        return f"{self.username} ({self.first_name} {self.last_name} - {self.role})"


# ================================
# MAGASIN (Multi-tenant)
# ================================

class Magasin(models.Model):
    nom = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    proprietaire = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name="magasins")
    adresse = models.TextField(blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    pays = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    devise = models.CharField(max_length=10, default="GNF")
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['proprietaire']),
            models.Index(fields=['actif']),
        ]
        
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


# ================================
# CATEGORIE PRODUIT
# ================================

class Categorie(models.Model):
    magasin = models.ForeignKey(Magasin, on_delete=models.CASCADE, related_name="categories")
    nom = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['magasin']),
            models.Index(fields=['nom']),
        ]
    
    def __str__(self):
        return self.nom


# ================================
# PRODUIT
# ================================

class Produit(models.Model):
    magasin = models.ForeignKey(Magasin, on_delete=models.CASCADE, related_name="produits")
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True)
    nom = models.CharField(max_length=255)
    code_barre = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    sku = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2)
    prix_vente = models.DecimalField(max_digits=10, decimal_places=2)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    quantite_stock = models.IntegerField(default=0)
    seuil_alerte = models.IntegerField(default=5)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_fabrication = models.DateField(blank=True, null=True)  # Date usine
    date_expiration = models.DateField(blank=True, null=True)   # Péremption
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['magasin', 'sku'], name='unique_sku_par_magasin'),
            models.UniqueConstraint(fields=['magasin', 'code_barre'], name='unique_code_barre_par_magasin'),
        ]
        indexes = [
            models.Index(fields=['magasin', 'nom']),
            models.Index(fields=['magasin', 'categorie']),
            models.Index(fields=['actif']),
            models.Index(fields=['date_creation']),
            models.Index(fields=['date_expiration']),
            models.Index(fields=['magasin', 'code_barre']),
            models.Index(fields=['magasin', 'sku']),
        ]


    def __str__(self):
        return self.nom


# ================================
# FOURNISSEUR
# ================================

class Fournisseur(models.Model):
    magasin = models.ForeignKey(Magasin, on_delete=models.CASCADE, related_name="fournisseurs")
    nom = models.CharField(max_length=255)
    prenom = models.CharField(max_length=255, blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['magasin']),
            models.Index(fields=['nom']),
        ]
    
    def __str__(self):
        return f"{self.nom} {self.prenom}"


# ================================
# ACHAT (Approvisionnement)
# ================================
from django.db import models, transaction
from django.db.models import Sum, F
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class Achat(models.Model):

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        TERMINE = 'TERMINE', 'Terminé'
        ANNULE = 'ANNULE', 'Annulé'

    magasin = models.ForeignKey(
        "Magasin",
        on_delete=models.CASCADE,
        related_name="achats",
        db_index=True
    )

    fournisseur = models.ForeignKey(
        "Fournisseur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    numero_facture = models.CharField(max_length=100)

    montant_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        db_index=True
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['magasin', 'numero_facture'],
                name='unique_facture_par_magasin'
            )
        ]
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['magasin', 'date_creation']),
            models.Index(fields=['statut']),
            models.Index(fields=['fournisseur']),
        ]

    def __str__(self):
        return f"{self.numero_facture} - {self.magasin}"

       
        
class LigneAchat(models.Model):

    achat = models.ForeignKey(
        Achat,
        on_delete=models.CASCADE,
        related_name="lignes"
    )

    produit = models.ForeignKey(
        "Produit",
        on_delete=models.PROTECT  # Important pour protéger historique
    )

    quantite = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )

    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['achat', 'produit'],
                name='unique_produit_par_achat'
            )
        ]
        indexes = [
            models.Index(fields=['achat']),
            models.Index(fields=['produit']),
        ]

    def __str__(self):
        return f"{self.produit} ({self.quantite})"
    
    def save(self, *args, **kwargs):
        self.total = self.quantite * self.prix_unitaire
        super().save(*args, **kwargs)
        
# ================================
# VENTE (POS)
# ================================
class Vente(models.Model):

    class Statut(models.TextChoices):
        COMPLETEE = 'COMPLETEE', 'Complétée'
        ANNULEE = 'ANNULEE', 'Annulée'

    magasin = models.ForeignKey(Magasin, on_delete=models.CASCADE, related_name="ventes")
    numero_facture = models.CharField(max_length=100)

    client_nom = models.CharField(max_length=255, blank=True, null=True)

    sous_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_tva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remise = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    mode_paiement = models.CharField(max_length=50)

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.COMPLETEE
    )

    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['magasin', 'numero_facture'],
                name='unique_vente_par_magasin'
            )
        ]
        indexes = [
            models.Index(fields=['magasin', 'date_creation']),
            models.Index(fields=['statut']),
            models.Index(fields=['mode_paiement']),
        ]


class LigneVente(models.Model):
    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    
    def save(self, *args, **kwargs):
        self.total = self.quantite * self.prix_unitaire
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['vente']),
            models.Index(fields=['produit']),
        ]
    
    def __str__(self):
        return f"{self.produit.nom} ({self.quantite})"


# ================================
# MOUVEMENT DE STOCK
# ================================

class MouvementStock(models.Model):
    TYPE_CHOIX = (
        ('ENTREE', 'Entrée'),
        ('SORTIE', 'Sortie'),
        ('AJUSTEMENT', 'Ajustement'),
    )

    magasin = models.ForeignKey(Magasin, on_delete=models.CASCADE, related_name="mouvements_stock")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    type_mouvement = models.CharField(max_length=20, choices=TYPE_CHOIX)
    quantite = models.IntegerField()
    reference = models.CharField(max_length=255, blank=True, null=True)
    cree_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['magasin', 'produit']),
            models.Index(fields=['type_mouvement']),
            models.Index(fields=['date_creation']),
        ]
    
    def __str__(self):
        return f"{self.produit.nom} - {self.type_mouvement}"
    
# ================================
# THEME ET PERSONNALISATION MAGASIN
# ================================

class ThemeMagasin(models.Model):

    magasin = models.OneToOneField(
        "Magasin",
        on_delete=models.CASCADE,
        related_name="theme"
    )

    couleur_principale = models.CharField(
        max_length=7,
        default="#1324db"
    )

    mode_sombre = models.BooleanField(default=False)

    logo = models.ImageField(
        upload_to="logos/",
        null=True,
        blank=True
    )

    class Meta:
        indexes = [
            models.Index(fields=['magasin']),
        ]
    
    def __str__(self):
        return f"Theme {self.magasin.nom}"
    
from django.db import models

class AuditLog(models.Model):

    class Action(models.TextChoices):
        CREATE = "CREATE", "Création"
        UPDATE = "UPDATE", "Modification"
        DELETE = "DELETE", "Suppression"

        VIEW = "VIEW", "Consultation"
        PRINT = "PRINT", "Impression"
        EXPORT = "EXPORT", "Export données"

        LOGIN = "LOGIN", "Connexion"

        LOGIN_FAILED_PASSWORD = "LOGIN_FAILED_PASSWORD", "Échec connexion (mot de passe)"
        LOGIN_FAILED_UNKNOWN = "LOGIN_FAILED_UNKNOWN", "Échec connexion (inconnu)"

        LOGOUT = "LOGOUT", "Déconnexion"

        CANCEL = "CANCEL", "Annulation"

        ACTIVATE = "ACTIVATE", "Activation"
        DISABLE = "DISABLE", "Désactivation"

        CUSTOM = "CUSTOM", "Action métier"

    utilisateur = models.ForeignKey(
        "Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs"
    )
    
    magasin = models.ForeignKey(
        "Magasin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    login_status = models.CharField(
    max_length=30,
    null=True,
    blank=True
)
    action = models.CharField(max_length=50, choices=Action.choices)
    modele = models.CharField(max_length=100)   # Produit, Vente...
    objet_id = models.CharField(max_length=50, null=True, blank=True)

    description = models.TextField(blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    url = models.CharField(max_length=255, blank=True)

    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["utilisateur", "date_action"]),
            models.Index(fields=['modele'], name='auditlog_modele_idx'),
            models.Index(fields=['modele', 'action'], name='auditlog_modele_action_idx'),
        ]
        ordering = ["-date_action"]

    def __str__(self):
        return f"{self.utilisateur} - {self.action} - {self.modele}"