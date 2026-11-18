"""Portable guest-template rendering with no Linux host dependencies."""


def render_script(c, text):
    values={'DEV':c.name('dev'),'DEV_UPPER':c.name('dev').upper(),
            'TARGET':c.name('target'),'TARGET_UPPER':c.name('target').upper(),
            'HOST_IP':c.ip('host'),'OPENSSH_SHA256':c.data['media'].get('openssh',{}).get('sha256','UNCONFIGURED').upper()}
    for key,value in values.items():text=text.replace('@@'+key+'@@',value)
    return text
