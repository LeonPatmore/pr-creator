#!/usr/bin/env python3
"""
Generate workflow diagrams for PR Creator using Graphviz.

Usage: python generate_workflow_diagram.py
"""

from graphviz import Digraph


def add_orchestrator_nodes(graph):
    graph.node('init', 'InitOrchestrator\n\n• Set defaults\n• Load prompts\n• Load secrets')
    graph.node('discover', 'DiscoverReposOrchestrator\n\n• Resolve repo list\n• Query Datadog if needed')
    graph.node('next_repo', 'NextRepoOrchestrator\n\n• Pop next repo\n• End if no repos left')
    graph.node('evaluate', 'EvaluateRelevanceOrchestrator\n\n• Clone for planning\n• AI evaluates relevance\n• Cache decision')
    graph.node('orchestrate', 'OrchestrateChange\n\n• AI agent plans change\n• Calls repo_change tool\n• Records PR results')


def add_orchestrator_edges(graph):
    graph.edge('init', 'discover')
    graph.edge('discover', 'next_repo', label='repos found')
    graph.edge('discover', 'orchestrate', label='no repos\n(MCP discovery)', style='dashed')
    graph.edge('next_repo', 'evaluate', label='has repo')
    graph.edge('evaluate', 'orchestrate', label='relevant')
    graph.edge('evaluate', 'next_repo', label='not relevant', style='dashed')
    graph.edge('orchestrate', 'next_repo', label='done')


def add_repo_change_nodes(graph):
    graph.node('naming', 'GenerateNames\n\n• Generate branch name\n• Create PR title\n• Create commit message')
    graph.node('workspace', 'WorkspaceRepo\n\n• Clone/checkout repo\n• Create/reuse branch')
    graph.node('apply', 'ApplyChanges\n\n• Run change agent (Cursor)\n• Apply guardrails\n• Handle review/CI feedback')
    graph.node('review', 'ReviewChanges\n\n• AI reviews changes\n• Check quality\n• Generate feedback')
    graph.node('submit', 'SubmitChanges\n\n• Commit changes\n• Push branch\n• Create/update PR')
    graph.node('wait', 'WaitForActions\n\n• Poll GitHub Actions\n• Check CI status\n• Collect logs')
    graph.node('cleanup', 'CleanupRepo\n\n• Remove workspace\n  (unless change_id set)')


def add_repo_change_edges(graph):
    graph.edge('naming', 'workspace')
    graph.edge('workspace', 'apply')
    graph.edge('apply', 'review')
    graph.edge('review', 'apply', label='needs changes\n(max attempts)', style='dashed', color='#d32f2f')
    graph.edge('review', 'submit', label='approved')
    graph.edge('submit', 'wait')
    graph.edge('wait', 'apply', label='CI failed\n(max attempts)', style='dashed', color='#d32f2f')
    graph.edge('wait', 'cleanup', label='CI passed\nor max attempts')


def create_orchestrator_workflow():
    dot = Digraph('orchestrator', format='png')
    dot.attr(rankdir='TB', bgcolor='white')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#e3f2fd', 
             fontname='Arial', fontsize='11')
    dot.attr('edge', fontname='Arial', fontsize='10')
    
    add_orchestrator_nodes(dot)
    add_orchestrator_edges(dot)
    return dot


def create_repo_change_workflow():
    dot = Digraph('repo_change', format='png')
    dot.attr(rankdir='TB', bgcolor='white')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#f3e5f5',
             fontname='Arial', fontsize='11')
    dot.attr('edge', fontname='Arial', fontsize='10')
    
    add_repo_change_nodes(dot)
    add_repo_change_edges(dot)
    return dot


def create_full_diagram():
    dot = Digraph('PR_Creator_Workflows', format='png')
    dot.attr(rankdir='TB', bgcolor='white', nodesep='0.8', ranksep='1.0')
    dot.attr('node', fontname='Arial', fontsize='11')
    dot.attr('edge', fontname='Arial', fontsize='10')

    with dot.subgraph(name='cluster_0') as c:
        c.attr(label='Orchestrator Workflow (Multi-repo coordination)', 
               style='rounded,filled', fillcolor='#e3f2fd', fontsize='14')
        c.attr('node', shape='box', style='rounded,filled', fillcolor='#bbdefb')
        add_orchestrator_nodes(c)

    with dot.subgraph(name='cluster_1') as c:
        c.attr(label='Repo Change Workflow (Single repo)', 
               style='rounded,filled', fillcolor='#f3e5f5', fontsize='14')
        c.attr('node', shape='box', style='rounded,filled', fillcolor='#e1bee7')
        add_repo_change_nodes(c)

    dot.node('tool', 'repo_change_tool()\n\n• Invoked by OrchestrateChange\n• Runs entire Repo Change workflow\n• Returns PR result',
             shape='ellipse', style='filled', fillcolor='#fff9c4')

    add_orchestrator_edges(dot)
    add_repo_change_edges(dot)

    dot.edge('orchestrate', 'tool', label='calls as tool', color='#ff6f00', penwidth='2', style='bold')
    dot.edge('tool', 'naming', label='starts workflow', color='#ff6f00', penwidth='2', style='bold')
    dot.edge('cleanup', 'orchestrate', label='returns result', color='#ff6f00', penwidth='2', style='bold,dashed')

    return dot


def main():
    create_full_diagram().render('workflow_diagram', cleanup=True)
    print('✓ workflow_diagram.png')
    
    create_orchestrator_workflow().render('orchestrator_workflow', cleanup=True)
    print('✓ orchestrator_workflow.png')
    
    create_repo_change_workflow().render('repo_change_workflow', cleanup=True)
    print('✓ repo_change_workflow.png')


if __name__ == '__main__':
    main()
