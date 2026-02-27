# doxoade/commands/sicdox.py
import click
# [DOX-UNUSED] from colorama import Style

@click.group('sicdox')
def sicdox_group():
    """SiCDox: Sistemas Cognitivos do Doxoade.
    Unificação de Intencionalidade, Raciocínio e Meta-Ação (Gold Edition).
    """
    pass

@sicdox_group.command('think')
@click.argument('prompt')
@click.pass_context
def think_cmd(ctx, prompt):
    """Raciocínio Rápido: Consulta ao System 1."""
    from .think import think
    ctx.invoke(think, prompt=prompt)

@sicdox_group.command('agent')
@click.pass_context
def agent_cmd_run(ctx):
    """Ciclo Ouroboros: Execução Autônoma e Aprendizado em Tempo Real."""
    from .agent import agent_cmd
    ctx.invoke(agent_cmd)

@sicdox_group.command('brain')
@click.option('--train', is_flag=True, help="Inicia ciclo de treinamento.")
@click.pass_context
def brain_cmd(ctx, train):
    """Gestão do Córtex: Pesos, Memória e Treinamento MTL."""
    from .brain import brain
    ctx.invoke(brain)

@sicdox_group.command('audit')
@click.pass_context
def audit_cmd(ctx):
    """Arquivologia Semântica: Dossiê de integridade e intenção."""
    from .intelligence import intelligence
    ctx.invoke(intelligence)

@sicdox_group.command('directory')
@click.argument('path', default='.')
def directory_cmd(path):
    """Propriocepção: Audita a visão de diretórios do SiCDox."""
    from ..diagnostic.directory_diagnose import auditar_percepcao_espacial
    auditar_percepcao_espacial(path)