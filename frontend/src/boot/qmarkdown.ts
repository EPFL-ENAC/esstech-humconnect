import { defineBoot } from '#q-app/wrappers';
import QMarkdownPlugin from '@quasar/quasar-ui-qmarkdown';
import '@quasar/quasar-ui-qmarkdown/dist/index.css';

export default defineBoot(({ app }) => {
    app.use(QMarkdownPlugin);
});
