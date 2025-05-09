# Generated by Django 5.1.6 on 2025-02-19 05:07

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='UploadedFile',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('filename', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='TwitchMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('user', models.CharField(max_length=255)),
                ('message_id', models.CharField(max_length=255, unique=True)),
                ('timestamp', models.CharField(max_length=255)),
                ('uptime', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.JSONField(default=list)),
                ('is_moderated', models.BooleanField(default=False)),
                ('sanction', models.CharField(blank=True, choices=[('Deleted', 'Deleted'), ('Timeout', 'Timeout'), ('Ban', 'Ban'), (None, 'None')], max_length=10, null=True)),
                ('duration', models.CharField(blank=True, max_length=20, null=True)),
                ('moderation_uptime', models.CharField(blank=True, max_length=255, null=True)),
                ('moderation_starttime', models.CharField(blank=True, max_length=255, null=True)),
                ('uploaded_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='compreve_django.uploadedfile')),
            ],
        ),
        migrations.CreateModel(
            name='StreamInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel', models.CharField(max_length=255)),
                ('title', models.TextField()),
                ('category', models.CharField(max_length=255)),
                ('language', models.CharField(max_length=10)),
                ('is_mature', models.BooleanField(default=False)),
                ('uptime', models.CharField(max_length=255)),
                ('start_time', models.CharField(max_length=255)),
                ('timestamp', models.CharField(max_length=255)),
                ('uploaded_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='compreve_django.uploadedfile')),
            ],
            options={
                'unique_together': {('uploaded_file', 'channel', 'title', 'category', 'start_time')},
            },
        ),
        migrations.CreateModel(
            name='ViewerCount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('viewer_count', models.IntegerField()),
                ('uptime', models.CharField(blank=True, max_length=255, null=True)),
                ('timestamp', models.CharField(max_length=255)),
                ('uploaded_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='compreve_django.uploadedfile')),
            ],
            options={
                'unique_together': {('uploaded_file', 'timestamp', 'viewer_count')},
            },
        ),
    ]
