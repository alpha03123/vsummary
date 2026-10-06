import { WorkspaceImportModal } from "@src/local-features/workspace/ui/WorkspaceImportModal";
import { render } from "@src/testing/renderWorkspace";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("WorkspaceImportModal", () => {
  it("does not import multiple files until selection is confirmed and imports only checked paths", async () => {
    const paths=['C:\\videos\\one.mp4','C:\\videos\\two.mp4'];
    const select=vi.fn().mockResolvedValue({sourcePaths:paths,hardlinkAvailable:true});
    const commit=vi.fn().mockResolvedValue({title:'Selected',videos:[{}]});
    render(<WorkspaceImportModal onClose={vi.fn()} onSelectLocalMedia={select} onImportLocalSeries={commit}/>);
    fireEvent.change(screen.getByPlaceholderText('例如：Agent Frameworks'),{target:{value:'Selected'}});
    fireEvent.click(screen.getByRole('button',{name:/未选择文件/}));
    await screen.findByText('已选择 2 个文件');
    fireEvent.click(screen.getByRole('button',{name:'导入',exact:true}));
    await screen.findByRole('dialog',{name:'确认导入'});
    expect(commit).not.toHaveBeenCalled();
    expect(screen.getAllByRole('checkbox').every(item=>item.getAttribute('aria-checked')==='true')).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'全不选'}));
    expect(screen.getByRole('button',{name:'导入所选视频'})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox',{name:'two.mp4'}));
    fireEvent.change(screen.getByRole('textbox',{name:'搜索待导入视频'}),{target:{value:'two'}});
    expect(screen.getAllByRole('checkbox')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button',{name:'导入所选视频'}));
    await waitFor(()=>expect(commit).toHaveBeenCalledWith('Selected',[paths[1]],'hardlink'));
  });
  it("defaults to an external reference for media outside the Blob storage disk", async () => {
    const onSelectLocalMedia = vi.fn().mockResolvedValue({
      sourcePaths: ["\\\\nas\\videos\\lesson.mp4"],
      hardlinkAvailable: false,
    });
    const onImportLocalSeries = vi.fn().mockResolvedValue({ title: "课程", videos: [{}] });
    render(
      <WorkspaceImportModal
        onClose={vi.fn()}
        onSelectLocalMedia={onSelectLocalMedia}
        onImportLocalSeries={onImportLocalSeries}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("例如：Agent Frameworks"), {
      target: { value: "课程" },
    });
    fireEvent.click(screen.getByRole("button", { name: /未选择文件/ }));

    await screen.findByText("lesson.mp4");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "导入" })));

    await waitFor(() => expect(onImportLocalSeries).toHaveBeenCalledWith("课程", ["\\\\nas\\videos\\lesson.mp4"], "external_reference"));
  });

  it("defaults to a hard link for media on the workspace disk", async () => {
    const onSelectLocalMedia = vi.fn().mockResolvedValue({
      sourcePaths: ["C:\\videos\\lesson.mp4"],
      hardlinkAvailable: true,
    });
    const onImportLocalSeries = vi.fn().mockResolvedValue({ title: "课程", videos: [{}] });
    render(
      <WorkspaceImportModal
        onClose={vi.fn()}
        onSelectLocalMedia={onSelectLocalMedia}
        onImportLocalSeries={onImportLocalSeries}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("例如：Agent Frameworks"), {
      target: { value: "课程" },
    });
    fireEvent.click(screen.getByRole("button", { name: /未选择文件/ }));

    await screen.findByText("lesson.mp4");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "导入" })));

    await waitFor(() => expect(onImportLocalSeries).toHaveBeenCalledWith("课程", ["C:\\videos\\lesson.mp4"], "hardlink"));
  });
});
