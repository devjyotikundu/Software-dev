from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('learning', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VocabularyItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=1)),
                ('term', models.CharField(help_text='The word/phrase in the language being learned.', max_length=100)),
                ('translation', models.CharField(help_text='The English meaning.', max_length=150)),
                ('lesson', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vocabulary_items',
                    to='learning.lesson',
                )),
            ],
            options={
                'ordering': ['lesson', 'order'],
            },
        ),
        migrations.CreateModel(
            name='QuizQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=1)),
                ('question', models.CharField(max_length=255)),
                ('answer', models.CharField(max_length=255)),
                ('lesson', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='quiz_questions',
                    to='learning.lesson',
                )),
            ],
            options={
                'ordering': ['lesson', 'order'],
            },
        ),
    ]
