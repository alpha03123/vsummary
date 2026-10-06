import {useState} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {WorkspaceToggleSwitch} from '@workspace/workspace/ui/shared/WorkspaceSettingsControls';

describe('WorkspaceToggleSwitch value contract', () => {
  it.each([false, true])('emits the next boolean when checked is %s', (checked) => {
    const onChange = vi.fn();
    render(<WorkspaceToggleSwitch checked={checked} onChange={onChange} ariaLabel="Multimodal"/>);
    fireEvent.click(screen.getByRole('button', {name: 'Multimodal'}));
    expect(onChange.mock.calls).toEqual([[!checked]]);
  });

  it('keeps controlled form values JSON-serializable across repeated clicks', () => {
    const save = vi.fn();
    function Form() {
      const [form, setForm] = useState({ai_summary_multimodal_enabled: false});
      return <WorkspaceToggleSwitch checked={form.ai_summary_multimodal_enabled} ariaLabel="Multimodal"
        onChange={value => {
          const next = {...form, ai_summary_multimodal_enabled: value};
          save(JSON.stringify(next));
          setForm(next);
        }}/>;
    }
    render(<Form/>);
    const button = screen.getByRole('button', {name: 'Multimodal'});
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(save.mock.calls).toEqual([
      ['{"ai_summary_multimodal_enabled":true}'],
      ['{"ai_summary_multimodal_enabled":false}'],
    ]);
  });

  it('does not change a disabled control', () => {
    const onChange = vi.fn();
    render(<WorkspaceToggleSwitch checked={false} disabled onChange={onChange} ariaLabel="Multimodal"/>);
    fireEvent.click(screen.getByRole('button', {name: 'Multimodal'}));
    expect(onChange).not.toHaveBeenCalled();
  });
});
