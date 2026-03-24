import React, { Fragment } from 'react';
import ForgeReconciler, { 
  Button, 
  Text, 
  Inline, 
  Box, 
  Heading, 
  Icon, 
  Stack 
} from '@forge/react';

const App = () => {
  const handleClick = async (action) => {
    console.log(`Clicked: ${action}`);
    // Aquí irá tu invoke('mi-funcion-backend')
  };

  return (
    <Fragment>
      <Stack space="space.200">
        {/* Encabezado con un poco de estilo */}
        <Box borderBlockEndWidth="border.width" borderBlockEndColor="color.border" paddingBlockEnd="space.100">
          <Heading as="h2">🚀 AI Actions Panel</Heading>
        </Box>

        <Text>Select an agent to process this issue:</Text>

        {/* Contenedor de botones con espaciado */}
        <Inline space="space.150" alignBlock="center">
          <Button 
            appearance="primary" 
            onClick={() => handleClick('discovery')}
            iconBefore={<Icon glyph="search" label="Discovery" />}
          >
            Run Discovery
          </Button>

          <Button 
            onClick={() => handleClick('architect')}
            iconBefore={<Icon glyph="component" label="Architect" />}
          >
            Design Architect
          </Button>

          <Button 
            onClick={() => handleClick('stories')}
            iconBefore={<Icon glyph="page" label="Stories" />}
          >
            Generate Stories
          </Button>
        </Inline>
      </Stack>
    </Fragment>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);