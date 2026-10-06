import {WorkspaceProviderSelect} from './WorkspaceSettingsControls';

/** Select with a vertical menu; opening it never expands the settings row. */
export function WorkspaceExpandableSelect({value,onChange,options,className='',disabled=false,ariaLabel}){
 const selected=options.find(option=>option.id===value);
 return <div className={`min-w-[140px] max-w-full ${className}`}>
  <WorkspaceProviderSelect value={value} onChange={onChange} options={options} disabled={disabled}
   ariaLabel={ariaLabel} hideGroupLabels align="end" optionLayout="vertical"/>
  {selected?.disabled&&selected.disabledReason&&<p className="mt-2 text-xs font-medium text-danger">{selected.disabledReason}</p>}
 </div>;
}
