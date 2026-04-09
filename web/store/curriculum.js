import { createStore } from './createStore.js';
import { curriculumApi } from '../api/curriculum.js';

export const curriculumStore = createStore({
  tracks: [],
  activeTrackSlug: 'k8s',
  tree: null,            // {modules:[{lessons:[{progress}]}]}
  loaded: false,
});

export async function loadCurriculum() {
  const tracks = await curriculumApi.listTracks();
  const items = tracks.items || [];
  let active = curriculumStore.state.activeTrackSlug;
  if (!items.find(t => t.slug === active)) {
    active = items[0]?.slug || null;
  }
  let tree = null;
  if (active) tree = await curriculumApi.getTrackTree(active);
  curriculumStore.patch({
    tracks: items,
    activeTrackSlug: active,
    tree,
    loaded: true,
  });
}

export async function reloadTree() {
  const slug = curriculumStore.state.activeTrackSlug;
  if (!slug) return;
  const tree = await curriculumApi.getTrackTree(slug);
  curriculumStore.patch({ tree });
}
