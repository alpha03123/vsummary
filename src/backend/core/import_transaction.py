"""Import adapters participating in one caller-owned SQL transaction."""
from contextlib import contextmanager


class TransactionSessions:
    def __init__(self, session):self.session=session
    @contextmanager
    def __call__(self):
        self.session.flush()
        yield self.session
    @contextmanager
    def begin(self):
        yield self.session
        self.session.flush()


class ImportBlobStore:
    """Track newly committed objects so failed database imports can release them."""
    def __init__(self, store):self.store=store;self.created=[];self.staged=[]
    def __getattr__(self,name):return getattr(self.store,name)
    def commit(self,staged,*,object_key):
        result=self.store.commit(staged,object_key=object_key);self.created.append(result);return result
    def put_staging(self,**kwargs):
        result=self.store.put_staging(**kwargs);self.staged.append(result);return result
    def rollback(self):
        for reference in self.created:self.store.delete(reference)
        for staged in self.staged:self.store.discard_staging(staged)
