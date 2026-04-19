# supermarcher/api/consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
import json
from channels.db import database_sync_to_async

from supermarcher.models import Produit

from supermarcher.models import Produit

class PanierConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        print(f"[CONNECT] Tentative de connexion pour user_id={self.user_id}")

        # ❌ Refuse connexion si utilisateur non authentifié
        if not user.is_authenticated or str(user.id) != self.user_id:
            print(f"[CONNECT] Connexion refusée pour user_id={self.user_id}, user.authenticated={user.is_authenticated}, user.id={getattr(user, 'id', None)}")
            await self.close()
            return

        # ✅ Définit le nom du groupe seulement si connexion valide
        self.group_name = f"panier_{self.user_id}"
        print(f"[CONNECT] Connexion acceptée, ajout au groupe {self.group_name}")

        # Rejoindre le groupe
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        print(f"[CONNECT] channel_name {self.channel_name} ajouté au groupe {self.group_name}")

        await self.accept()

    async def disconnect(self, close_code):
        print(f"[DISCONNECT] user_id={getattr(self, 'user_id', 'unknown')} close_code={close_code}")
        # ⚡ Vérifie que group_name existe avant de l'utiliser
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            print(f"[DISCONNECT] channel_name {self.channel_name} retiré du groupe {self.group_name}")

    async def receive(self, text_data):
        print(f"[RECEIVE] user_id={getattr(self, 'user_id', 'unknown')} text_data={text_data}")
        
        data = json.loads(text_data)
        code = (data.get("code_barre") or "").strip()

        # ❌ Code-barres vide
        if not code:
            await self.send(text_data=json.dumps({
                "status": "error",
                "detail": "Code-barres manquant"
            }))
            return

        user = self.scope.get("user")

        # 🔍 Recherche produit (async safe)
        produit = await self.get_produit(user, code)

        if produit:
            response = {
                "status": "found",
                "id": produit.id,
                "nom": produit.nom,
                "prix": str(produit.prix_vente),
                "quantite": produit.quantite_stock,
                "taux_tva": str(produit.taux_tva),
                "actif": produit.actif,
                "date_expiration": produit.date_expiration.isoformat() if produit.date_expiration else None,
                "code_barre": produit.code_barre,
            }
        else:
            response = {
                "status": "not_found"
            }

        # 🔁 Envoyer au groupe
        if hasattr(self, "group_name"):
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'panier_update',
                    'message': response
                }
            )
            print(f"[RECEIVE] Message envoyé au groupe {self.group_name}: {response}")

    # 🔧 Fonction DB (obligatoire pour éviter erreur async)
    @database_sync_to_async
    def get_produit(self, user, code):
        try:
            magasin = user.magasin
        except:
            return None
        from supermarcher.models import Produit
        return Produit.objects.filter(
            magasin=magasin,
            code_barre=code
        ).first()
        
    async def panier_update(self, event):
        # Envoie le message à ce client
        print(f"[PANIER_UPDATE] Envoi au client: {event['message']}")
        await self.send(text_data=json.dumps(event['message']))
        

import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ThemeConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.magasin_id = self.scope['url_route']['kwargs']['magasin_id']
        self.group_name = f"theme_{self.magasin_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    # 🔥 MESSAGE REÇU DU SERVEUR
    async def theme_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))