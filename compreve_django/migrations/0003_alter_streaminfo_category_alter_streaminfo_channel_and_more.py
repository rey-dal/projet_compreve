# Generated by Django 5.1.5 on 2025-03-19 08:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('compreve_django', '0002_alter_streaminfo_unique_together'),
    ]

    operations = [
        migrations.AlterField(
            model_name='streaminfo',
            name='category',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='channel',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='is_mature',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='language',
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='start_time',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='timestamp',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='title',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='uploaded_file',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='compreve_django.uploadedfile'),
        ),
        migrations.AlterField(
            model_name='streaminfo',
            name='uptime',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='duration',
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='is_moderated',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='message',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='message_id',
            field=models.CharField(max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='moderation_starttime',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='moderation_uptime',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='sanction',
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='status',
            field=models.JSONField(null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='timestamp',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='uploaded_file',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='compreve_django.uploadedfile'),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='uptime',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='twitchmessage',
            name='user',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='uploadedfile',
            name='filename',
            field=models.CharField(max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='viewercount',
            name='timestamp',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='viewercount',
            name='uploaded_file',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='compreve_django.uploadedfile'),
        ),
        migrations.AlterField(
            model_name='viewercount',
            name='uptime',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='viewercount',
            name='viewer_count',
            field=models.IntegerField(null=True),
        ),
    ]
