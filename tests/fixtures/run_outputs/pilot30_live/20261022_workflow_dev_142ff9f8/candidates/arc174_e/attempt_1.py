def __init__(self,p,e=None):
    self.p=p
    self.e=e
    if self.e==None:
        self.mod=self.p
    else:
        self.mod=self.p**self.e
