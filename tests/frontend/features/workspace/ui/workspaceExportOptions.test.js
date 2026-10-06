import {describe,test,expect} from 'vitest';
import {buildWorkspaceToolExportActions} from '@workspace/workspace/ui/workspaceToolExports';

describe('host export options',()=>{
 test('restricts Cloud overview exports while keeping default Local exports',()=>{
  const input={toolId:'overview',activeSeries:{id:'series'},selectedVideo:{id:'video',hasTranscript:true},
   tools:{overview:{generated:true}},summary:{chapters:[{image_url:'/api/image'}]}};
  expect(buildWorkspaceToolExportActions(input)).toHaveLength(5);
  const selected=buildWorkspaceToolExportActions({...input,allowedExports:{overview:['mixed.md','summary-with-screenshots.zip']},resourceUrl:path=>'https://host.example'+path});
  expect(selected.map(item=>item.href)).toEqual(['https://host.example/api/videos/series/video/exports/summary-with-screenshots.zip','https://host.example/api/videos/series/video/exports/mixed.md']);
 });
});
