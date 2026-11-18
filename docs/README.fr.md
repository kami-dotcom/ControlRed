# Contrôle réseau 4.1

[English](../README.md) · [Español](../LEEME.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [Português](README.pt.md) · [Русский](README.ru.md)

Tableau de bord local pour Windows permettant de détecter les appareils, d’identifier leur fabricant par adresse MAC et de gérer leur accès.

## Démarrage

1. Installez [Npcap](https://npcap.com/#download).
2. Fermez une ancienne version avec **Quitter**.
3. Lancez **ControlRed-v4.1.exe**, en tant qu’administrateur si nécessaire.
4. Choisissez votre carte Ethernet ou Wi-Fi physique.
5. Sélectionnez **Français** dans la barre de langues en haut.

La langue est mémorisée dans le navigateur. Les noms personnalisés et les autorisations sont conservés. Demostracion.cmd ouvre un environnement simulé.

## Gestion des accès

Le **Blocage manuel** permet de choisir les appareils individuellement. En mode **Liste d’autorisation**, un blocage est demandé pour chaque appareil détecté sans autorisation. Cliquez sur **Autoriser** ou **Autoriser une adresse MAC** pour accorder l’accès. Le routeur et ce PC sont protégés.

Gardez ce PC et le programme en marche ; vous pouvez fermer l’onglet. Les blocages restent actifs jusqu’à leur désactivation ou la fermeture du programme. IPv6 nécessite la détection des adresses et du routeur. Les protections réseau peuvent limiter le blocage.

Une recherche au démarrage ; ensuite, utilisez Actualiser le réseau. Le contrôle continue sans recherches périodiques. Le trafic local observé peut révéler de nouveaux appareils ; actualisez le réseau si un appareil manque.

L’efficacité dépend du réseau et des protections des appareils. Une demande de blocage ne prouve pas que la connexion Internet a été coupée. Utilisez le programme uniquement sur les réseaux que vous êtes autorisé à administrer.

Consultez le [README en anglais](../README.md) pour le code source, les tests et la compilation.
