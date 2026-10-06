import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {WorkspaceDialog} from '@workspace/workspace/ui/shared/WorkspaceDialog';

describe('WorkspaceDialog interactions',()=>{
 it('keeps an accessible name with a custom header and closes from the built-in button',()=>{
  const onClose=vi.fn();
  render(<WorkspaceDialog open title="Account login" header={<img alt="Brand" src="/brand.svg"/>} onClose={onClose}><input aria-label="Email"/></WorkspaceDialog>);
  expect(screen.getByRole('dialog',{name:'Account login'})).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'关闭'}));
  expect(onClose).toHaveBeenCalledTimes(1);
 });

 it('blocks close, Escape, backdrop dismissal and form submission while pending',()=>{
  const onClose=vi.fn(),onSubmit=vi.fn();
  render(<WorkspaceDialog open title="Saving" pending onClose={onClose} onSubmit={onSubmit}><input aria-label="Name"/></WorkspaceDialog>);
  const dialog=screen.getByRole('dialog',{name:'Saving'});
  expect(screen.getByRole('button',{name:'关闭'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'关闭'}));
  fireEvent.keyDown(dialog,{key:'Escape'});
  fireEvent.pointerDown(dialog.parentElement,{button:0});
  fireEvent.pointerUp(dialog.parentElement,{button:0});
  fireEvent.submit(dialog);
  expect(onClose).not.toHaveBeenCalled();
  expect(onSubmit).not.toHaveBeenCalled();
 });

 it('portals the dialog outside its host container',()=>{
  const {container}=render(<aside><WorkspaceDialog open title="Sidebar account" onClose={vi.fn()}/></aside>);
  const dialog=screen.getByRole('dialog',{name:'Sidebar account'});
  expect(container).not.toContainElement(dialog);
  expect(document.body).toContainElement(dialog);
 });

 it('submits the form without allowing the close button to submit',()=>{
  const onClose=vi.fn(),onSubmit=vi.fn();
  render(<WorkspaceDialog open title="Rename" onClose={onClose} onSubmit={onSubmit}/>);
  fireEvent.click(screen.getByRole('button',{name:'关闭'}));
  expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.submit(screen.getByRole('dialog',{name:'Rename'}));
  expect(onSubmit).toHaveBeenCalledTimes(1);
 });
});
