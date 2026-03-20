import React, { Fragment } from 'react';
import ForgeReconciler, { Button, Text } from '@forge/react';

const App = () => {
  const handleClick = async (action) => {
    // Por ahora solo queremos que el panel renderice y sea clickeable.
    // Más adelante conectaremos el resolver (invoke) para ejecutar acciones.
    console.log(`Clicked: ${action}`);

    // Aquí luego llamas tu webhook
    // await fetch("https://tu-api.com", {...})
  };


 return (
    <Fragment>
      <Text>🚀 AI Actions Panel</Text>
      
      <Button onClick={() => handleClick("discovery")}>
      Run Discovery Agent
    </Button>

        <Button onClick={() => handleClick("architect")}>
      Run Design Architect
    </Button>

    <Button onClick={() => handleClick("stories")}>
      Generate Stories & Tasks
    </Button>
    </Fragment>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
