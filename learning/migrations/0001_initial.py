from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Lesson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lesson_order', models.PositiveIntegerField()),
                ('title', models.CharField(max_length=150)),
                ('contents', models.TextField(help_text='The teaching content shown to the learner.')),
                ('language', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lessons',
                    to='learning.language',
                )),
            ],
            options={
                'ordering': ['language', 'lesson_order'],
                'unique_together': {('language', 'lesson_order')},
            },
        ),
        migrations.CreateModel(
            name='LearningProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('proficiency', models.CharField(
                    choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')],
                    default='beginner',
                    max_length=20,
                )),
                ('current_lesson', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='learning.lesson',
                )),
                ('language', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profiles',
                    to='learning.language',
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='learning_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='LearningProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('not_started', 'Not started'), ('in_progress', 'In progress'), ('completed', 'Completed')],
                    default='in_progress',
                    max_length=20,
                )),
                ('completed', models.BooleanField(default=False)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('lesson', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='progress_records',
                    to='learning.lesson',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='progress_records',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'unique_together': {('user', 'lesson')},
            },
        ),
    ]
