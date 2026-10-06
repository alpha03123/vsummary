"""Owned, expiring import previews. Previewing never creates a library resource."""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import json
import shutil
import time

from filelock import FileLock, Timeout
from backend.core.ids import new_ulid
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


class ImportPreviewStore:
    def __init__(self, root, context, *, ttl_seconds=3600):
        self.root=Path(root).resolve();self.context=context;self.ttl_seconds=ttl_seconds
        self.root.mkdir(parents=True,exist_ok=True)

    def path(self, token):
        if not token or Path(token).name!=token or not token.isalnum():
            raise ValueError('Invalid import preview token.')
        return self.root/token

    def create(self, kind, title, items, *, linked=None):
        token=new_ulid();directory=self.path(token);directory.mkdir()
        owned=[]
        for index,item in enumerate(items):
            item=dict(item)
            if kind=='files':
                target=directory/'files'/str(index)/Path(item['path']).name
                target.parent.mkdir(parents=True)
                shutil.move(str(item['path']),target)
                item['path']=str(target)
            owned.append(item)
        plan={'token':token,'kind':kind,'title':title,'items':owned,'linked':asdict(linked) if linked else None,
            'workspace_id':self.context.workspace_id,'actor_id':self.context.actor_id,'expires_at':time.time()+self.ttl_seconds}
        temporary=directory/'plan.tmp'
        temporary.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
        temporary.replace(directory/'plan.json')
        return self.public(plan)

    @staticmethod
    def public(plan):
        return {'token':plan['token'],'title':plan['title'],'expires_at':plan['expires_at'],
            'items':[{key:value for key,value in item.items() if key!='path'} for item in plan['items']]}

    @contextmanager
    def locked(self, token):
        directory=self.path(token)
        with FileLock(str(self.root/(token+'.lock'))):
            if not (directory/'plan.json').is_file():raise LookupError('导入预览不存在或已过期，请重新选择。')
            plan=json.loads((directory/'plan.json').read_text(encoding='utf-8'))
            if (plan['workspace_id'],plan['actor_id'])!=(self.context.workspace_id,self.context.actor_id):
                raise PermissionError('导入预览不属于当前账号。')
            if plan['expires_at']<time.time():
                shutil.rmtree(directory)
                raise LookupError('导入预览已过期，请重新选择。')
            yield plan

    @staticmethod
    def selected(plan, ids):
        if not ids or len(ids)!=len(set(ids)) or not set(ids)<={item['id'] for item in plan['items']}:
            raise ValueError('请选择有效的视频，至少勾选一个。')
        return [item for item in plan['items'] if item['id'] in ids]

    @staticmethod
    def linked(plan, ids):
        ImportPreviewStore.selected(plan,ids)
        data=dict(plan['linked'])
        data['videos']=[LinkedVideo(**item) for item in data['videos']
            if LinkedVideo(**item).video_id in ids]
        return LinkedSeries(**data)

    def discard(self, token):
        with self.locked(token):shutil.rmtree(self.path(token))

    @staticmethod
    def expire(root):
        root=Path(root)
        for manifest in root.glob('*/plan.json'):
            try:
                with FileLock(str(root/(manifest.parent.name+'.lock')),timeout=0):
                    plan=json.loads(manifest.read_text(encoding='utf-8'))
                    if plan['expires_at']<time.time():shutil.rmtree(manifest.parent)
            except Timeout:
                continue
