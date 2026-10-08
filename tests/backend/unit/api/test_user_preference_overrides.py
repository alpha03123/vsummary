from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import shutil
import pytest
from pydantic import ValidationError
from backend.core.preferences import UserPreferences, bind_user_preferences, preference_cache_key
from backend.video_summary.infrastructure.config.user_preferences import load_effective_settings, resolve_user_settings
from backend.video_summary.infrastructure.config.settings import load_settings


def test_whitelist_is_strict_and_does_not_mutate_deployment_settings(tmp_path):
    shutil.copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',tmp_path/'settings.toml.example')
    base=load_settings(tmp_path/'settings.toml',tmp_path)
    base=replace(base,openai=replace(base.openai,api_key='deployment-only',model='original'))
    selected=resolve_user_settings(base,{'ai_summary_multimodal_enabled':True,'answer_detail_level':'short','auto_generate_artifacts':['mindmap'],'model_profile':'terra'},{'terra':'configured-terra'})
    assert selected.generation.ai_summary_multimodal_enabled
    assert selected.agent_context.answer_detail_level=='short'
    assert selected.generation.auto_generate_artifacts==('mindmap',)
    assert selected.openai.model=='configured-terra'
    assert selected.openai.api_key==base.openai.api_key
    assert base.openai.model=='original'
    assert base.generation.auto_generate_artifacts==()
    with pytest.raises(ValidationError):
        UserPreferences.model_validate({'api_key':'user-key'})
    with pytest.raises(ValidationError):
        UserPreferences.model_validate({'ai_summary_multimodal_enabled':'false'})
    with pytest.raises(ValueError):
        resolve_user_settings(base,{'model_profile':'unconfigured'},{})


@pytest.mark.parametrize("enabled", [False, True])
def test_cloud_multimodal_preference_controls_images_without_changing_local_defaults(tmp_path, enabled):
    shutil.copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',tmp_path/'settings.toml.example')
    base=load_settings(tmp_path/'settings.toml',tmp_path)
    base=replace(base,generation=replace(base.generation,chapter_visual_mode='screenshots',
        note_visual_mode='screenshots',mindmap_visual_input='frames',cards_visual_input='frames'))
    effective=resolve_user_settings(base,{'ai_summary_multimodal_enabled':enabled})
    assert effective.generation.chapter_visual_mode == ('screenshots' if enabled else 'off')
    assert effective.generation.note_visual_mode == ('screenshots' if enabled else 'off')
    assert effective.generation.cards_visual_input == ('frames' if enabled else 'none')
    assert effective.generation.mindmap_visual_input == ('frames' if enabled else 'none')
    assert base.generation.note_visual_mode == 'screenshots'


def test_simultaneous_actors_receive_independent_effective_settings_and_local_defaults(tmp_path):
    shutil.copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',tmp_path/'settings.toml.example')
    path=tmp_path/'settings.toml'
    base=load_settings(path,tmp_path)
    def read(enabled,level):
        with bind_user_preferences({'ai_summary_multimodal_enabled':enabled,'answer_detail_level':level}):
            settings=load_effective_settings(path,tmp_path)
            return settings.generation.ai_summary_multimodal_enabled,settings.agent_context.answer_detail_level,preference_cache_key()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(read,True,'short'); b=pool.submit(read,False,'long')
        first,second=a.result(),b.result()
    assert first[:2]==(True,'short') and second[:2]==(False,'long')
    assert first[2]!=second[2]
    assert load_effective_settings(path,tmp_path)==base
