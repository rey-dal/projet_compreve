from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator, EmptyPage, InvalidPage
from django.db.models import Q
from .models import TwitchMessage, StreamInfo, ViewerCount, UploadedFile
import os
import json
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from django.conf import settings
from math import ceil
import shutil
from xml.dom import minidom
import io
from django.utils.timezone import make_aware
from django.db import connection  # Direct database connection
from django.db.models import F
from django.db.models import Value
from django.db.models.functions import Lower
from django.db.models import IntegerField, Value, Case, When
from django.db.models.functions import Cast
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.db.models import Q, Case, When, Value, IntegerField
from django.db import IntegrityError
from django.db import transaction
from itertools import chain
import ast  # Safely parse the string list into Python lists
from django.db.models import OuterRef, Subquery
import xml.etree.ElementTree as ET
import logging
import re
import urllib.parse
from django.db.models.functions import Coalesce


def login_view(request):
    return render(request, 'login.html')


"""
    Vue Django pour gérer l'affichage des fichiers téléchargés.
    Cette vue permet de récupérer les noms de fichiers uniques, de filtrer les résultats en fonction d'une requête de recherche,
    de paginer les résultats, et de renvoyer les données sous forme de JSON pour les requêtes AJAX ou de rendre un template pour les requêtes normales.
"""
def fichiers_view(request):
    # Récupérer les noms de fichiers uniques depuis la base de données.
    # distinct garantit que chaque nom de fichier est unique.
    files = UploadedFile.objects.values_list('filename', flat=True).distinct()

    # Gérer le filtrage par recherche
    # Récupérer la requête de recherche depuis les paramètres GET de la requête.
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # Si une requête de recherche est présente, filtrer les fichiers dont le nom contient la requête.
        # '__icontains' permet une recherche insensible à la casse.
        files = UploadedFile.objects.filter(filename__icontains=search_query).values_list('filename', flat=True)

    # Pagination des résultats
    # Créer un objet Paginator pour paginer les résultats, affichant 15 fichiers par page.
    paginator = Paginator(files, 15)
    # Récupérer le numéro de page depuis les paramètres GET de la requête, par défaut 1.
    page_number = request.GET.get('page', 1)

    # Obtenir l'objet Page pour la page actuelle.
    page_obj = paginator.get_page(page_number)


    # Vérifier si la requête est une requête AJAX
    # Si l'en-tête 'X-Requested-With' est défini sur 'XMLHttpRequest', cela signifie que la requête est une requête AJAX.
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Retourner une réponse JSON contenant les fichiers de la page actuelle, le nombre total de pages, et le numéro de la page actuelle.
        return JsonResponse({
            'files': [{'name': filename} for filename in page_obj],
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number
        })

    # Rendre le template 'fichiers.html' pour les requêtes normales (non-AJAX)
    # Passer les fichiers de la page actuelle, le nombre total de pages, et le numéro de la page actuelle au contexte du template.
    return render(request, 'fichiers.html', {
        'files': [{'name': filename} for filename in page_obj],
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number
    })



"""
    Vue Django pour gérer le téléversement des fichiers JSON vers la BDD.
    Cette vue permet de recevoir des fichiers JSON via une requête POST, de les valider,
    et de stocker les données contenues dans ces fichiers dans la base de données.
"""

def upload_json(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    if 'files' not in request.FILES:
        return JsonResponse({'success': False, 'erreur': 'aucun fichier uploadé'})

    # Récupérer la liste des fichiers téléchargés
    uploaded_files = request.FILES.getlist('files')
    results = {"success": [], "failed": []}

    # Parcourir chaque fichier téléchargé
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name
        # Vérifier que le fichier a une extension .json
        if not file_name.endswith('.json'):
            results["failed"].append({"file": file_name, "error": "File must be a JSON file"})
            continue

        try:
            file_content = uploaded_file.read().decode('utf-8')
            data = json.loads(file_content)
            # Utiliser une transaction atomique pour garantir que toutes les opérations de base de données réussissent ou échouent ensemble
            with transaction.atomic():
                uploaded_file_obj, created = UploadedFile.objects.get_or_create(filename=file_name)

                # Initialiser des listes pour stocker les objets à créer dans la base de données
                messages = []
                stream_infos = []
                viewer_counts = []
                valid_sanctions = {"Deleted", "Timeout", "Ban", "null"}

                # Parcourir les données de streaminfo dans le fichier JSON
                for stream in data.get('streaminfos', []):
                    channel_name = stream.get("channel")
                    if not channel_name:  # If channel is None or empty string
                        print(f"Warning: Missing channel name in stream info: {stream}")
                        continue  # Skip this stream info

                    # Create StreamInfo with the original channel name from JSON
                    stream_info = StreamInfo(
                        uploaded_file=uploaded_file_obj,
                        channel=channel_name,  # Use exact channel name from JSON
                        title=stream.get("title", ""),
                        category=stream.get("category", ""),
                        language=stream.get("language", ""),
                        is_mature=bool(stream.get("isMature", False)),
                        uptime=stream.get("uptime", ""),
                        start_time=stream.get("startTime", ""),
                        timestamp=stream.get("timestamp", "")
                    )
                    stream_infos.append(stream_info)

                # Vérifier qu'il y a au moins une entrée de streaminfo
                if not stream_infos:
                    raise ValueError("Ce fichier ne peut pas être uploadé car il ne contient pas (streaminfos)")

                # Create all StreamInfo objects at once
                StreamInfo.objects.bulk_create(stream_infos)

                # Now process messages with the correct channel info
                for msg in data.get('allMessages', []):
                    # Get the timestamp for this message
                    msg_timestamp = msg.get("timestamp", "")
                    
                    # Create the message with a reference to its file
                    message = TwitchMessage(
                        uploaded_file=uploaded_file_obj,
                        message=msg.get("message", ""),
                        user=msg.get("user", ""),
                        message_id=msg.get("messageId", ""),
                        timestamp=msg_timestamp,
                        uptime=msg.get("uptime", ""),
                        status=msg.get("status", None),
                        is_moderated=bool(msg.get("isModerated", False)),
                        sanction=msg.get("sanction", None),
                        duration=msg.get("duration", None),
                        moderation_uptime=msg.get("moderationUptime", None),
                        moderation_starttime=msg.get("moderationStartTime", None)
                    )
                    messages.append(message)


                # Parcourir les données de comptage de spectateurs dans le fichier JSON
                for viewer in data.get('viewercount', []):
                    viewer_counts.append(ViewerCount(
                        uploaded_file=uploaded_file_obj,
                        viewer_count=viewer.get('viewerCount', 0),
                        uptime=viewer.get('uptime', ''),
                        timestamp=viewer.get('timestamp', '')
                    ))

            # Créer les objets TwitchMessage et ViewerCount dans la base de données en une seule opération
                if messages:
                    TwitchMessage.objects.bulk_create(messages)
                if viewer_counts:
                    ViewerCount.objects.bulk_create(viewer_counts)

            # Ajouter le nom du fichier aux résultats réussis
            results["success"].append(file_name)

        except json.JSONDecodeError:
            results["failed"].append({"file": file_name, "error": "Format JSON Invalide"})
        except IntegrityError:
            results["failed"].append({"file": file_name, "error": "Ce fichier existe déja dans la base de données."})
        except Exception as e:
            results["failed"].append({"file": file_name, "error": str(e)})

    # Renvoyer les résultats sous forme de réponse JSON
    return JsonResponse(results)


"""
    Évalue en toute sécurité les chaînes de caractères ressemblant à du JSON en listes Python.
    Cette fonction est utilisée pour convertir une chaîne représentant une liste en une véritable liste Python.
"""
def safe_eval(value):

    if isinstance(value, list):
        return value

    if isinstance(value, str) and value.startswith("["):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [value]

    return [value]


def get_request_param(request, param_name, default_value=None):
    """Récupère un paramètre de la requête GET ou renvoie une valeur par défaut."""
    return request.GET.get(param_name, default_value)

def get_common_request_params(request):
    """Récupère les paramètres communs à toutes les vues."""
    return {
        'file': get_request_param(request, "file"),
        'searchMessage': get_request_param(request, "searchMessage", ""),
        'searchUser': get_request_param(request, "searchUser", ""),
        'sort': get_request_param(request, "sort", "-timestamp"),
        'page': int(get_request_param(request, "page", 1)),
        'selected_channels' : request.GET.getlist("channels"),
        'filters': json.loads(get_request_param(request, "filters", "{}").replace("'", '"'))
    }



"""
    Vue Django pour gérer l'affichage et le filtrage des messages Twitch stockés dans la base de données.
    Cette vue permet de récupérer les messages associés à un fichier spécifique, d'appliquer divers filtres,
    de trier les résultats, et de paginer les données pour une navigation efficace. Elle peut renvoyer les données
    sous forme de JSON pour les requêtes AJAX ou rendre un template HTML pour les requêtes normales.
"""

def bases_de_donnees_view(request):
    query_params = get_common_request_params(request)
    # Définir le nombre de messages à afficher par page
    per_page = 50

    try:
        filters = query_params['filters'] if query_params['filters'] else {}
    except json.JSONDecodeError:
        filters = {}

    if not query_params['file']:
        return redirect('fichiers')

    # Filtrer les messages Twitch associés au fichier spécifié
    messages = TwitchMessage.objects.filter(uploaded_file__filename=query_params['file'])

    # Appliquer les filtres basés sur les paramètres de la requête
    if filters.get('modere'):
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    if filters.get('supprime'):
        # Filtrer les messages en fonction de leur état de suppression
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        elif filters['supprime'] == 'false':
            messages = messages.exclude(sanction="Deleted")

    if filters.get('status') and filters['status'].lower() != "all":
        # Filtrer les messages en fonction de leur statut
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')


    if query_params['searchMessage']:
        # Filtrer les messages dont le contenu correspond à la recherche ( par message)
        messages = messages.filter(message__icontains=query_params['searchMessage'])

    if query_params['searchUser']:
        # Filtrer les messages dont le contenu correspond à la recherche (par utilisateur)
        messages = messages.filter(user__icontains=query_params['searchUser'])


    sort_by = query_params['sort']
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = '-timestamp'

    if sort_field == "duration":
        # Si le tri est basé sur la durée, annoter les messages avec une valeur numérique pour la durée
        messages = messages.annotate(
            duration_int=Case(
                #attribue une valeur de 9999999 a lifetime afin de garantie sa position dans le tri
                When(duration="lifetime", then=Value(9999999)),
                default=Cast('duration', IntegerField()),
                output_field=IntegerField(),
            )
        ).order_by('-duration_int' if sort_by.startswith('-') else 'duration_int')
    elif sort_field == "channel":
        messages = messages.order_by(f"{'-' if sort_by.startswith('-') else ''}channel")
    else:
        messages = messages.order_by(sort_by)

    # Pagination des résultats
    paginator = Paginator(messages, per_page)
    messages_page = paginator.get_page(query_params['page'])


    all_statuses = TwitchMessage.objects.values_list("status", flat=True)


    flat_statuses = set(chain.from_iterable(safe_eval(status) for status in all_statuses if status))


    unique_statuses = sorted(flat_statuses)

    # Vérifier si la requête est une requête AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        messages_data = []
        for msg in messages_page:
            msg_dict = {
                'id': msg.id,
                'message': msg.message,
                'user': msg.user,
                'message_id': msg.message_id,
                'uptime': msg.uptime,
                'timestamp': msg.timestamp,
                'status': msg.status,
                'uploaded_file__filename': msg.uploaded_file.filename,
                'is_moderated': msg.is_moderated,
                'sanction': msg.sanction,
                'duration': msg.duration
            }
            messages_data.append(msg_dict)
        return JsonResponse({
            'messages': messages_data,
            'total_pages': paginator.num_pages,
            'current_page': messages_page.number,
            'has_previous': messages_page.has_previous(),
            'has_next': messages_page.has_next(),
            'previous_page_number': messages_page.previous_page_number() if messages_page.has_previous() else None,
            'next_page_number': messages_page.next_page_number() if messages_page.has_next() else None,
            'all_statuses': list(unique_statuses)
        })
    # Rendre le template HTML pour les requêtes normales
    return render(request, 'bases_de_données.html', {
        'messages': messages_page,
        'filename': query_params['file'],
        'searchMessage': query_params['searchMessage'],
        'searchUser': query_params['searchUser'],
        'sort_by': sort_by,
        'current_page': query_params['page'],
        'total_pages': paginator.num_pages,
        'has_previous': messages_page.has_previous(),
        'has_next': messages_page.has_next(),
        'all_statuses': unique_statuses,
        'page_range': range(max(1, messages_page.number - 2), min(paginator.num_pages + 1, messages_page.number + 3))
    })


"""
    Vue Django pour gérer la recherche et l'affichage des messages Twitch avec divers filtres et options de tri.
    Cette vue permet aux utilisateurs de rechercher des messages en fonction de plusieurs critères, de les trier,
    et de les paginer pour une navigation efficace. Elle peut renvoyer les données sous forme de JSON pour les requêtes AJAX
    ou rendre un template HTML pour les requêtes normales. Elle fournit également des statistiques sur les messages.
"""

def recherche_view(request):
    query_params = get_common_request_params(request)
    per_page = 50

    # Get all channels for the filter dropdown - exclude empty channels
    all_channels = StreamInfo.objects.exclude(
        channel__isnull=True
    ).exclude(
        channel__exact=''
    ).values_list('channel', flat=True).distinct().order_by('channel')
    
    # Get messages with channel info
    messages = TwitchMessage.objects.all()
    print(f"Total messages before filtering: {messages.count()}")  # Debug log
    
    # Get the channel directly from the StreamInfo that was created during JSON upload
    messages = messages.annotate(
        channel=Subquery(
            StreamInfo.objects.filter(
                uploaded_file=OuterRef('uploaded_file')
            ).values('channel')[:1]
        )
    ).select_related('uploaded_file')

    # Apply channel filtering
    selected_channels = request.GET.getlist('channels', [])
    print(f"Selected channels from request: {selected_channels}")  # Debug log

    if selected_channels:
        messages = messages.filter(
            uploaded_file__streaminfo__channel__in=selected_channels
        ).distinct()
        print(f"Total messages after channel filter: {messages.count()}")  # Debug log

    # Handle filters
    try:
        filters = query_params['filters'] if query_params['filters'] else {}
    except json.JSONDecodeError:
        filters = {}

    # Apply moderation filter
    if filters.get('modere') in ['true', 'false']:
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    # Apply deletion filter
    if filters.get('supprime') in ['true', 'false']:
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        else:
            messages = messages.exclude(sanction="Deleted")

    # Apply status filter
    if filters.get('status'):
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')


    if query_params['searchMessage']:
        # Filtrer les messages dont le contenu correspond à la recherche ( par message)
        messages = messages.filter(message__icontains=query_params['searchMessage'])

    if query_params['searchUser']:
        # Filtrer les messages dont le contenu correspond à la recherche (par utilisateur)
        messages = messages.filter(user__icontains=query_params['searchUser'])


    sort_by = query_params['sort']
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status', 'moderation_starttime', 'moderation_uptime', 'channel']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = '-timestamp'

    if sort_field == "duration":
        messages = messages.annotate(
            duration_int=Case(
                When(duration="lifetime", then=Value(9999999)),
                default=Cast('duration', IntegerField()),
                output_field=IntegerField(),
            )
        ).order_by('-duration_int' if sort_by.startswith('-') else 'duration_int')
    elif sort_field == "channel":
        # Get the latest channel for each message before sorting
        messages = messages.annotate(
            latest_channel=Subquery(
                StreamInfo.objects.filter(
                    timestamp__lte=OuterRef('timestamp')
                ).order_by('-timestamp').values('channel')[:1]
            )
        ).order_by(f"{'-' if sort_by.startswith('-') else ''}latest_channel")
    else:
        messages = messages.order_by(sort_by)

    # Get total count before pagination
    total_count = messages.count()
    total_pages = (total_count + per_page - 1) // per_page

    # Apply pagination
    page = int(request.GET.get('page', 1))
    paginator = Paginator(messages, per_page)
    try:
        messages_page = paginator.page(page)
    except (EmptyPage, InvalidPage):
        messages_page = paginator.page(1)
        page = 1

    # Get all unique statuses
    all_statuses = TwitchMessage.objects.values_list("status", flat=True)
    flat_statuses = set(chain.from_iterable(safe_eval(status) for status in all_statuses if status))
    unique_statuses = sorted(flat_statuses)

    # Calculate statistics
    total_messages = messages.count()
    deleted_messages = messages.filter(sanction="Deleted").count()
    total_users = messages.values("user").distinct().count()
    total_channels = StreamInfo.objects.values("channel").distinct().count()

    # Handle AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        messages_data = []
        for msg in messages_page:
            msg_dict = {
                'id': msg.id,
                'message': msg.message,
                'user': msg.user,
                'message_id': msg.message_id,
                'uptime': msg.uptime,
                'timestamp': msg.timestamp,
                'status': msg.status,
                'is_moderated': msg.is_moderated,
                'sanction': msg.sanction,
                'duration': msg.duration,
                'moderation_starttime': msg.moderation_starttime,
                'moderation_uptime': msg.moderation_uptime,
                'channel': msg.channel
            }
            messages_data.append(msg_dict)
        return JsonResponse({
            "messages": messages_data,
            "total_pages": total_pages,
            "current_page": page,
            "has_previous": messages_page.has_previous(),
            "has_next": messages_page.has_next(),
            "previous_page_number": messages_page.previous_page_number() if messages_page.has_previous() else None,
            "next_page_number": messages_page.next_page_number() if messages_page.has_next() else None,
            "all_statuses": list(unique_statuses),
            "filters": filters,
            "filters_str": filters,
            "stats": {
                "total_messages": total_messages,
                "deleted_messages": deleted_messages,
                "total_users": total_users,
                "total_channels": total_channels
            }
        })

    # Render template for normal requests
    return render(request, "recherche.html", {
        "messages": messages_page,
        "total_pages": total_pages,
        "current_page": page,
        "search_query": query_params['searchMessage'],
        "search_user": query_params['searchUser'],
        "sort_by": sort_by,
        "filters": filters,
        "filters_str": filters,
        "all_statuses": unique_statuses,
        "all_channels": all_channels,
        "selected_channels": request.GET.getlist("channels"),
        "total_messages": total_messages,
        "deleted_messages": deleted_messages,
        "total_users": total_users,
        "total_channels": total_channels,
        'page_range': range(max(1, messages_page.number - 2), min(paginator.num_pages + 1, messages_page.number + 3))
    })



"""
    Vue Django pour supprimer un fichier et toutes les données associées de la base de données.
    Cette vue accepte uniquement les requêtes POST contenant le nom du fichier à supprimer.
    Elle supprime les enregistrements liés au fichier dans les tables TwitchMessage, StreamInfo, et ViewerCount,
    puis supprime le fichier lui-même.
"""
def delete_filename(request):
    if request.method == "POST":
        filename = request.POST.get("filename", "").strip()
        print(f"Received filename for deletion: {filename}")

        if not filename:
            return JsonResponse({"status": "error", "message": "No filename provided"}, status=400)


        try:
            uploaded_file = UploadedFile.objects.get(filename=filename)
        except UploadedFile.DoesNotExist:
            return JsonResponse({"status": "error", "message": "File not found"}, status=404)


        twitch_messages_deleted, _ = TwitchMessage.objects.filter(uploaded_file=uploaded_file).delete()
        stream_info_deleted, _ = StreamInfo.objects.filter(uploaded_file=uploaded_file).delete()
        viewer_count_deleted, _ = ViewerCount.objects.filter(uploaded_file=uploaded_file).delete()

        print(f"Deleted {twitch_messages_deleted} TwitchMessage records.")
        print(f"Deleted {stream_info_deleted} StreamInfo records.")
        print(f"Deleted {viewer_count_deleted} ViewerCount records.")

        # Suppression de l'instance de UploadedFile elle-même
        uploaded_file.delete()
        print(f"Deleted UploadedFile: {filename}")


        # Renvoyer une réponse JSON indiquant le succès de la suppression
        return JsonResponse({
            "status": "success",
            "message": f"Deleted {twitch_messages_deleted + stream_info_deleted + viewer_count_deleted} records, including {filename}"
        })

    # Si la méthode de requête n'est pas POST, renvoyer une réponse d'erreur
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

"""
    Vue Django pour exporter des messages filtrés au format JSON.
    Cette vue récupère les messages Twitch associés à un fichier spécifique, applique des filtres et des tris,
    puis prépare les données pour être téléchargées sous forme de fichier JSON.
"""
def export_filtered_json(request):
    query_params = get_common_request_params(request)

    try:
        filters = query_params['filters'] if query_params['filters'] else {}
    except json.JSONDecodeError:
        filters = {}

    if not query_params['file']:
        return JsonResponse({"error": "Filename is required"}, status=400)

    # Get streamer name from filename by removing date and extension
    filename = query_params['file']
    streamer_name = filename.split('_')[0]  # Get the first part before underscore

    messages = TwitchMessage.objects.filter(uploaded_file__filename=query_params['file'])

    if filters.get('modere'):
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    if filters.get('supprime'):
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        elif filters['supprime'] == 'false':
            messages = messages.exclude(sanction="Deleted")

    if filters.get('status') and filters['status'].lower() != "all":
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    if query_params['searchMessage']:
        messages = messages.filter(message__icontains=query_params['searchMessage'])

    if query_params['searchUser']:
        messages = messages.filter(user__icontains=query_params['searchUser'])

    sort_by = query_params['sort']
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = '-timestamp'

    messages = messages.order_by(sort_by)

    # Fetch des ViewerCount et StreamInfos
    viewer_counts = ViewerCount.objects.filter(uploaded_file__filename=query_params['file']).order_by('timestamp')
    stream_infos = StreamInfo.objects.filter(uploaded_file__filename=query_params['file']).order_by('-timestamp')

    # préparation des données JSON
    data = {
        "allMessages": [
            {
                "user": msg.user,
                "message": msg.message,
                "messageId": msg.message_id,
                "timestamp": msg.timestamp,
                "uptime": msg.uptime,
                "status": msg.status,
                "isModerated": msg.is_moderated,
                "sanction": msg.sanction,
                "duration": msg.duration,
                "moderation_uptime": msg.moderation_uptime,
                "moderation_starttime": msg.moderation_starttime,
            }
            for msg in messages
        ],
        "timeouts": [],
        "bans": [],
        "streaminfos": [
            {
                "channel": stream.channel,
                "title": stream.title,
                "category": stream.category,
                "language": stream.language,
                "isMature": stream.is_mature,
                "uptime": stream.uptime,
                "startTime": stream.start_time,
                "timestamp": stream.timestamp,
            }
            for stream in stream_infos
        ],
        "viewercount": [
            {
                "viewerCount": vc.viewer_count,
                "uptime": vc.uptime,
                "timestamp": vc.timestamp,
            }
            for vc in viewer_counts
        ],
    }


    response = HttpResponse(
        json.dumps(data, indent=4, ensure_ascii=False),
        content_type="application/json"
    )
    response['Content-Disposition'] = f'attachment; filename="{streamer_name}_filtered.json"'
    return response



"""
    Vue Django pour exporter des messages filtrés au format CSV.
    Cette vue récupère les messages Twitch associés à un fichier spécifique, applique des filtres et des tris,
    puis prépare les données pour être téléchargées sous forme de fichier CSV.
"""

def export_filtered_csv(request):
    query_params = get_common_request_params(request)
    try:
        filters = query_params['filters'] if query_params['filters'] else {}
    except json.JSONDecodeError:
        filters = {}

    if not query_params['file']:
        return JsonResponse({"error": "Filename is required"}, status=400)

    # Get streamer name from filename by removing date and extension
    filename = query_params['file']
    streamer_name = filename.split('_')[0]  # Get the first part before underscore

    messages = TwitchMessage.objects.filter(uploaded_file__filename=query_params['file'])

    if filters.get('modere'):
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    if filters.get('supprime'):
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        elif filters['supprime'] == 'false':
            messages = messages.exclude(sanction="Deleted")

    if filters.get('status') and filters['status'].lower() != "all":
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    if query_params['searchMessage']:
        messages = messages.filter(message__icontains=query_params['searchMessage'])

    if query_params['searchUser']:
        messages = messages.filter(user__icontains=query_params['searchUser'])

    sort_by = query_params['sort']
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = 'timestamp'

    messages = messages.order_by(sort_by)

    csv_file_name = streamer_name
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{csv_file_name}_filtered.csv"'
    # Créer un objet writer pour écrire dans le fichier CSV
    writer = csv.writer(response)
    writer.writerow(["User", "Message", "Message ID", "Timestamp", "Uptime", "Status", "Is Moderated", "Sanction", "Duration", "Moderation Uptime", "Moderation Start Time"])

    writer.writerow(['FILTRES SÉLECTIONNÉS'])
    writer.writerow(['Date d\'export', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    if query_params['searchMessage']:
        writer.writerow(['Message', query_params['searchMessage']])
    if query_params['searchUser']:
        writer.writerow(['Utilisateur', query_params['searchUser']])
    if filters.get('modere'):
        writer.writerow(['Modéré', filters['modere']])
    if filters.get('supprime'):
        writer.writerow(['Supprimé', filters['supprime']])
    if filters.get('status'):
        writer.writerow(['Status', filters['status']])
    writer.writerow(['Tri', sort_by])
    writer.writerow([])  # Empty row for spacing

    for msg in messages:
        writer.writerow([
            msg.user,
            msg.message,
            msg.message_id,
            msg.timestamp,
            msg.uptime,
            msg.status,
            msg.is_moderated,
            msg.sanction,
            msg.duration,
            msg.moderation_uptime,
            msg.moderation_starttime,
        ])

    return response



"""
    Vue Django pour exporter des messages filtrés au format XML.
    Cette vue récupère les messages Twitch associés à un fichier spécifique, applique des filtres et des tris,
    puis prépare les données pour être téléchargées sous forme de fichier XML.
"""
def export_filtered_xml(request):
    query_params = get_common_request_params(request)

    try:
        filters = query_params['filters'] if query_params['filters'] else {}
    except json.JSONDecodeError:
        filters = {}

    if not query_params['file']:
        return JsonResponse({"error": "Filename is required"}, status=400)

    # Get streamer name from filename by removing date and extension
    filename = query_params['file']
    streamer_name = filename.split('_')[0]  # Get the first part before underscore

    messages = TwitchMessage.objects.filter(uploaded_file__filename=query_params['file'])

    if filters.get('modere') in ['true', 'false']:
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    if filters.get('supprime') in ['true', 'false']:
        messages = messages.filter(sanction="Deleted") if filters['supprime'] == 'true' else messages.exclude(sanction="Deleted")

    if filters.get('status') and filters['status'].lower() != "all":
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    # Appliquer les filtres de recherche
    if query_params['searchMessage']:
        messages = messages.filter(message__icontains=query_params['searchMessage'])
    if query_params['searchUser']:
        messages = messages.filter(user__icontains=query_params['searchUser'])

    # Valider et appliquer le tri
    sort_by = query_params.get('sort', '-timestamp')  # Default to -timestamp
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = 'timestamp' if not sort_by.startswith('-') else '-timestamp'

    messages = messages.order_by(sort_by)

    viewer_counts = ViewerCount.objects.filter(uploaded_file__filename=query_params['file']).order_by('timestamp')
    stream_infos = StreamInfo.objects.filter(uploaded_file__filename=query_params['file']).order_by('-timestamp')

    root = ET.Element("data")

    all_messages = ET.SubElement(root, "allMessages")
    for msg in messages:
        message_elem = ET.SubElement(all_messages, "message")
        ET.SubElement(message_elem, "user").text = str(msg.user or "")
        ET.SubElement(message_elem, "content").text = str(msg.message or "")
        ET.SubElement(message_elem, "messageId").text = str(msg.message_id or "")
        ET.SubElement(message_elem, "timestamp").text = str(msg.timestamp or "")
        ET.SubElement(message_elem, "uptime").text = str(msg.uptime or "")
        ET.SubElement(message_elem, "status").text = str(msg.status or "")
        ET.SubElement(message_elem, "isModerated").text = str(msg.is_moderated)
        ET.SubElement(message_elem, "sanction").text = str(msg.sanction or "")
        ET.SubElement(message_elem, "duration").text = str(msg.duration or "")
        ET.SubElement(message_elem, "moderationUptime").text = str(msg.moderation_uptime or "")
        ET.SubElement(message_elem, "moderationStarttime").text = str(msg.moderation_starttime or "")


    stream_infos_elem = ET.SubElement(root, "streaminfos")
    for stream in stream_infos:
        stream_elem = ET.SubElement(stream_infos_elem, "streaminfo")
        ET.SubElement(stream_elem, "channel").text = str(stream.channel or "")
        ET.SubElement(stream_elem, "title").text = str(stream.title or "")
        ET.SubElement(stream_elem, "category").text = str(stream.category or "")
        ET.SubElement(stream_elem, "language").text = str(stream.language or "")
        ET.SubElement(stream_elem, "isMature").text = str(stream.is_mature).lower()
        ET.SubElement(stream_elem, "uptime").text = str(stream.uptime or "")
        ET.SubElement(stream_elem, "startTime").text = str(stream.start_time or "")
        ET.SubElement(stream_elem, "timestamp").text = str(stream.timestamp or "")

    viewer_counts_elem = ET.SubElement(root, "viewercount")
    for vc in viewer_counts:
        viewer_elem = ET.SubElement(viewer_counts_elem, "viewer")
        ET.SubElement(viewer_elem, "viewerCount").text = str(vc.viewer_count or "")
        ET.SubElement(viewer_elem, "uptime").text = str(vc.uptime or "")
        ET.SubElement(viewer_elem, "timestamp").text = str(vc.timestamp or "")

    # Créer un arbre XML et écrire dans la réponse
    xml_file_name = streamer_name
    tree = ET.ElementTree(root)
    response = HttpResponse(content_type="application/xml")
    response['Content-Disposition'] = f'attachment; filename="{xml_file_name}_filtered.xml"'
    tree.write(response, encoding='utf-8', xml_declaration=True)

    return response

"""
    Vue Django pour exporter tous les messages filtrés au format JSON.
    Cette vue permet de récupérer tous les messages Twitch ( elle s'applique pour l'export des messages depuis la vue globale), d'appliquer des filtres et des tris,
    puis de préparer les données pour être téléchargées sous forme de fichier JSON.
    
"""
def export_global_filtered_json(request):
    search_message = request.GET.get('searchMessage', '')
    search_user = request.GET.get('searchUser', '')
    sort_by = request.GET.get('sort', '-timestamp')
    channels = [ch.strip() for ch in request.GET.getlist('channels') if ch and ch.strip()]
    
    # Parse filters from JSON
    try:
        filters_str = request.GET.get('filters', '')
        filters = json.loads(filters_str) if filters_str else {}
    except json.JSONDecodeError:
        filters = {}

    # Create filter information
    filter_info = {
        "exportInfo": {
            "dateExport": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filtres": {
                "message": search_message if search_message else None,
                "utilisateur": search_user if search_user else None,
                "modere": filters.get('modere'),
                "supprime": filters.get('supprime'),
                "status": filters.get('status'),
                "chaines": channels if channels else None,
                "tri": sort_by
            }
        }
    }

    # Get messages with their channels
    streaminfo_subquery = StreamInfo.objects.filter(
        uploaded_file=OuterRef('uploaded_file')
    ).values('channel')[:1]

    messages = TwitchMessage.objects.annotate(
        channel=Subquery(streaminfo_subquery)
    )

    # Apply channel filtering
    if channels:
        print(f"Selected channels: {channels}")  # Debug log
        messages = messages.filter(channel__in=channels).distinct()  # Strip whitespace
        print(f"Total messages after channel filter: {messages.count()}")  # Debug log

    # Apply moderation filter
    if filters.get('modere') in ['true', 'false']:
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    # Apply deletion filter
    if filters.get('supprime') in ['true', 'false']:
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        else:
            messages = messages.exclude(sanction="Deleted")

    # Apply status filter
    if filters.get('status'):
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    # Apply search filters
    if search_message:
        messages = messages.filter(message__icontains=search_message)
    if search_user:
        messages = messages.filter(user__icontains=search_user)

    # Apply sorting
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status', 'moderation_starttime', 'moderation_uptime', 'channel']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = '-timestamp'

    if sort_field == "duration":
        messages = messages.annotate(
            duration_int=Case(
                When(duration="lifetime", then=Value(9999999)),
                default=Cast('duration', IntegerField()),
                output_field=IntegerField(),
            )
        ).order_by('-duration_int' if sort_by.startswith('-') else 'duration_int')
    elif sort_field == "channel":
        # Get the latest channel for each message before sorting
        messages = messages.annotate(
            latest_channel=Subquery(
                StreamInfo.objects.filter(
                    timestamp__lte=OuterRef('timestamp')
                ).order_by('-timestamp').values('channel')[:1]
            )
        ).order_by(f"{'-' if sort_by.startswith('-') else ''}latest_channel")
    else:
        messages = messages.order_by(sort_by)

    # Prepare export data with filter information at the top
    data = {
        **filter_info,  # Add filter information at the top
        "allMessages": [
            {
                "user": msg.user,
                "message": msg.message,
                "messageId": msg.message_id,
                "timestamp": msg.timestamp,
                "uptime": msg.uptime,
                "status": msg.status,
                "isModerated": msg.is_moderated,
                "sanction": msg.sanction,
                "duration": msg.duration,
                "moderation_uptime": msg.moderation_uptime,
                "moderation_starttime": msg.moderation_starttime,
                "channel": msg.channel
            }
            for msg in messages
        ]
    }

    response = HttpResponse(
        json.dumps(data, indent=4, ensure_ascii=False),
        content_type="application/json"
    )
    response['Content-Disposition'] = 'attachment; filename="filtered_messages.json"'
    return response

def export_global_filtered_csv(request):
    search_message = request.GET.get('searchMessage', '')
    search_user = request.GET.get('searchUser', '')
    sort_by = request.GET.get('sort', '-timestamp')
    channels = request.GET.getlist('channels')
    
    # Parse filters from JSON
    try:
        filters_str = request.GET.get('filters', '')
        filters = json.loads(filters_str) if filters_str else {}
    except json.JSONDecodeError:
        filters = {}

    messages = TwitchMessage.objects.all()


    if channels:
        print(f"Selected channels: {channels}")  # Debug log
        messages = messages.filter(uploaded_file__streaminfo__channel__in=channels).distinct()  # Strip whitespace
        print(f"Total messages after channel filter: {messages.count()}")  # Debug log

    if filters.get('modere'):
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    if filters.get('supprime'):
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        elif filters['supprime'] == 'false':
            messages = messages.exclude(sanction="Deleted")

    if filters.get('status') and filters['status'].lower() != "all":
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    if search_message:
        messages = messages.filter(message__icontains=search_message)

    if search_user:
        messages = messages.filter(user__icontains=search_user)

    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = 'timestamp'

    messages = messages.order_by(sort_by)

    # Suivre les identifiants de message uniques pour éviter les doublons
    unique_message_ids = set()
    unique_messages = []
    for msg in messages:
        if msg.message_id not in unique_message_ids:
            unique_message_ids.add(msg.message_id)
            unique_messages.append(msg)

    # Préparer le fichier CSV
    csv_file_name = "filtered_messages"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{csv_file_name}.csv"'
    # Créer un objet writer pour écrire dans le fichier CSV
    writer = csv.writer(response)
    writer.writerow(["User", "Message", "Message ID", "Timestamp", "Uptime", "Status", "Is Moderated", "Sanction", "Duration", "Moderation Uptime", "Moderation Start Time", "Channel"])
    
    writer.writerow(['FILTRES SÉLECTIONNÉS'])
    writer.writerow(['Date d\'export', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    if search_message:
        writer.writerow(['Message', search_message])
    if search_user:
        writer.writerow(['Utilisateur', search_user])
    if filters.get('modere'):
        writer.writerow(['Modéré', filters['modere']])
    if filters.get('supprime'):
        writer.writerow(['Supprimé', filters['supprime']])
    if filters.get('status'):
        writer.writerow(['Status', filters['status']])
    if channels:
        writer.writerow(['Chaînes', ', '.join(channels)])
    writer.writerow(['Tri', sort_by])
    writer.writerow([])  # Empty row for spacing
    
    # Écrire les données des messages dans le fichier CSV
    for msg in unique_messages:
        channel = StreamInfo.objects.filter(uploaded_file=msg.uploaded_file).first().channel if msg.uploaded_file else 'Unknown'
        writer.writerow([
            msg.user,
            msg.message,
            msg.message_id,
            msg.timestamp,
            msg.uptime,
            msg.status,
            msg.is_moderated,
            msg.sanction,
            msg.duration,
            msg.moderation_uptime,
            msg.moderation_starttime,
            channel
        ])

    return response

def export_global_filtered_xml(request):
    search_message = request.GET.get('searchMessage', '')
    search_user = request.GET.get('searchUser', '')
    sort_by = request.GET.get('sort', '-timestamp')
    channels = request.GET.getlist('channels')
    
    # Parse filters from JSON
    try:
        filters_str = request.GET.get('filters', '')
        filters = json.loads(filters_str) if filters_str else {}
    except json.JSONDecodeError:
        filters = {}

    # Get messages with their channels
    streaminfo_subquery = StreamInfo.objects.filter(
        uploaded_file=OuterRef('uploaded_file')
    ).values('channel')[:1]

    messages = TwitchMessage.objects.annotate(
        channel=Subquery(streaminfo_subquery)
    )

    # Apply channel filtering
    if channels:
        messages = messages.filter(channel__in=[ch.strip() for ch in channels]).distinct()

    # Apply moderation filter
    if filters.get('modere') in ['true', 'false']:
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    # Apply deletion filter
    if filters.get('supprime') in ['true', 'false']:
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        else:
            messages = messages.exclude(sanction="Deleted")

    # Apply status filter
    if filters.get('status'):
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    # Apply search filters
    if search_message:
        messages = messages.filter(message__icontains=search_message)
    if search_user:
        messages = messages.filter(user__icontains=search_user)

    # Apply sorting
    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status', 'moderation_starttime', 'moderation_uptime', 'channel']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = '-timestamp'

    if sort_field == "duration":
        messages = messages.annotate(
            duration_int=Case(
                When(duration="lifetime", then=Value(9999999)),
                default=Cast('duration', IntegerField()),
                output_field=IntegerField(),
            )
        ).order_by('-duration_int' if sort_by.startswith('-') else 'duration_int')
    elif sort_field == "channel":
        # Get the latest channel for each message before sorting
        messages = messages.annotate(
            latest_channel=Subquery(
                StreamInfo.objects.filter(
                    timestamp__lte=OuterRef('timestamp')
                ).order_by('-timestamp').values('channel')[:1]
            )
        ).order_by(f"{'-' if sort_by.startswith('-') else ''}latest_channel")
    else:
        messages = messages.order_by(sort_by)

    root = ET.Element('data')
    
    # Add export information at the top
    export_info = ET.SubElement(root, 'exportInfo')
    ET.SubElement(export_info, 'dateExport').text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Add filter information
    filtres = ET.SubElement(export_info, 'filtres')
    if search_message:
        ET.SubElement(filtres, 'message').text = search_message
    if search_user:
        ET.SubElement(filtres, 'utilisateur').text = search_user
    if filters.get('modere'):
        ET.SubElement(filtres, 'modere').text = filters['modere']
    if filters.get('supprime'):
        ET.SubElement(filtres, 'supprime').text = filters['supprime']
    if filters.get('status'):
        ET.SubElement(filtres, 'status').text = filters['status']
    if channels:
        chaines = ET.SubElement(filtres, 'chaines')
        for channel in channels:
            ET.SubElement(chaines, 'chaine').text = channel
    ET.SubElement(filtres, 'tri').text = sort_by

    # Add messages
    messages_element = ET.SubElement(root, 'messages')
    for msg in messages:
        message = ET.SubElement(messages_element, 'message')
        ET.SubElement(message, 'user').text = str(msg.user)
        ET.SubElement(message, 'content').text = str(msg.message)
        ET.SubElement(message, 'messageId').text = str(msg.message_id)
        ET.SubElement(message, 'timestamp').text = str(msg.timestamp)
        ET.SubElement(message, 'uptime').text = str(msg.uptime)
        ET.SubElement(message, 'status').text = str(msg.status)
        ET.SubElement(message, 'isModerated').text = str(msg.is_moderated)
        ET.SubElement(message, 'sanction').text = str(msg.sanction)
        ET.SubElement(message, 'duration').text = str(msg.duration)
        ET.SubElement(message, 'moderationUptime').text = str(msg.moderation_uptime)
        ET.SubElement(message, 'moderationStarttime').text = str(msg.moderation_starttime)
        ET.SubElement(message, 'channel').text = str(msg.channel)

    # Create the XML string with proper formatting
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    
    response = HttpResponse(xml_str, content_type='application/xml')
    response['Content-Disposition'] = 'attachment; filename="filtered_messages.xml"'
    return response

def export_global_filtered_csv(request):
    # Récupérer les paramètres de recherche et de tri depuis la requête GET
    search_message = request.GET.get('searchMessage', '')
    search_user = request.GET.get('searchUser', '')
    sort_by = request.GET.get('sort', '-timestamp')
    channels = [ch.strip() for ch in request.GET.getlist('channels') if ch and ch.strip()]
    
    filters = request.GET.get('filters', '{}')
    try:
        filters = json.loads(filters) if filters else {}
    except json.JSONDecodeError:
        filters = {}

    messages = TwitchMessage.objects.all()


    if channels:
        print(f"Selected channels: {channels}")  # Debug log
        messages = messages.filter(uploaded_file__streaminfo__channel__in=channels).distinct()  # Strip whitespace
        print(f"Total messages after channel filter: {messages.count()}")  # Debug log

    if filters.get('modere'):
        messages = messages.filter(is_moderated=(filters['modere'] == 'true'))

    if filters.get('supprime'):
        if filters['supprime'] == 'true':
            messages = messages.filter(sanction="Deleted")
        elif filters['supprime'] == 'false':
            messages = messages.exclude(sanction="Deleted")

    if filters.get('status') and filters['status'].lower() != "all":
        selected_status = filters['status'].strip("[]'")
        messages = messages.filter(status__icontains=f'"{selected_status}"')

    if search_message:
        messages = messages.filter(message__icontains=search_message)

    if search_user:
        messages = messages.filter(user__icontains=search_user)

    valid_sort_fields = ['id', 'message', 'user', 'timestamp', 'uptime', 'is_moderated', 'sanction', 'duration', 'status']
    sort_field = sort_by.lstrip('-')

    if sort_field not in valid_sort_fields:
        sort_by = 'timestamp'

    messages = messages.order_by(sort_by)

    # Suivre les identifiants de message uniques pour éviter les doublons
    unique_message_ids = set()
    unique_messages = []
    for msg in messages:
        if msg.message_id not in unique_message_ids:
            unique_message_ids.add(msg.message_id)
            unique_messages.append(msg)

    # Préparer le fichier CSV
    csv_file_name = "filtered_messages"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{csv_file_name}.csv"'
    # Créer un objet writer pour écrire dans le fichier CSV
    writer = csv.writer(response)
    writer.writerow(["User", "Message", "Message ID", "Timestamp", "Uptime", "Status", "Is Moderated", "Sanction", "Duration", "Moderation Uptime", "Moderation Start Time", "Channel"])
    
    writer.writerow(['FILTRES SÉLECTIONNÉS'])
    writer.writerow(['Date d\'export', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    if search_message:
        writer.writerow(['Message', search_message])
    if search_user:
        writer.writerow(['Utilisateur', search_user])
    if filters.get('modere'):
        writer.writerow(['Modéré', filters['modere']])
    if filters.get('supprime'):
        writer.writerow(['Supprimé', filters['supprime']])
    if filters.get('status'):
        writer.writerow(['Status', filters['status']])
    if channels:
        writer.writerow(['Chaînes', ', '.join(channels)])
    writer.writerow(['Tri', sort_by])
    writer.writerow([])  # Empty row for spacing
    
    # Écrire les données des messages dans le fichier CSV
    for msg in unique_messages:
        channel = StreamInfo.objects.filter(uploaded_file=msg.uploaded_file).first().channel if msg.uploaded_file else 'Unknown'
        writer.writerow([
            msg.user,
            msg.message,
            msg.message_id,
            msg.timestamp,
            msg.uptime,
            msg.status,
            msg.is_moderated,
            msg.sanction,
            msg.duration,
            msg.moderation_uptime,
            msg.moderation_starttime,
            channel
        ])

    return response