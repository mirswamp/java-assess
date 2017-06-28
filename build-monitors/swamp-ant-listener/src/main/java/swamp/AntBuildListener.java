/*
 *  Licensed to the Apache Software Foundation (ASF) under one or more
 *  contributor license agreements.  See the NOTICE file distributed with
 *  this work for additional information regarding copyright ownership.
 *  The ASF licenses this file to You under the Apache License, Version 2.0
 *  (the "License"); you may not use this file except in compliance with
 *  the License.  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 */

package swamp;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.Hashtable;
import java.util.LinkedList;
import java.util.Stack;
import java.util.Enumeration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.tools.ant.taskdefs.Javac;
import org.apache.tools.ant.types.Path;
import org.apache.tools.ant.types.PatternSet;
import org.apache.tools.ant.util.DOMElementWriter;
import org.apache.tools.ant.util.FileUtils;
import org.apache.tools.ant.util.JavaEnvUtils;
import org.apache.tools.ant.util.StringUtils;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.Text;
import org.apache.tools.ant.BuildEvent;
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.BuildListener;
//import org.apache.tools.ant.Evaluable;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.RuntimeConfigurable;
import org.apache.tools.ant.Task;

/**
 * Generates a file in the current directory with
 * an XML description of what happened during a build.
 * The default filename is "log.xml", but this can be overridden
 * with the property <code>XmlLogger.file</code>.
 *
 * This implementation assumes in its sanity checking that only one
 * thread runs a particular target/task at a time. This is enforced
 * by the way that parallel builds and antcalls are done - and
 * indeed all but the simplest of tasks could run into problems
 * if executed in parallel.
 *
 * @see Project#addBuildListener(BuildListener)
 */
public class AntBuildListener implements BuildListener {

    /** DocumentBuilder to use when creating the document to start with. */
    private static DocumentBuilder builder = getDocumentBuilder();

    /**
     * Returns a default DocumentBuilder instance or throws an
     * ExceptionInInitializerError if it can't be created.
     *
     * @return a default DocumentBuilder instance.
     */
    private static DocumentBuilder getDocumentBuilder() {
        try {
            return DocumentBuilderFactory.newInstance().newDocumentBuilder();
        } catch (Exception exc) {
            throw new ExceptionInInitializerError(exc);
        }
    }

    /** property to define if the listener output has to be written to a specific file. */
    private static final String LISTENER_OUT_FILENAME_PROP = "swamp.build.monitor.output";
    
    /** default output filename if the user does not define LISTENER_OUT_FILENAME_PROP property. */
    private static final String LISTENER_DEFAULT_OUT_FILENAME = "ant_build_artifacts_info.xml";
    
    private static final String BUILD_TAG = "build-artifacts";
    
    private static final String TASK_TAG = "java-compile";
    private static final String SRC_DIR_TAG = "srcdir";
    private static final String SRC_FILE_TAG = "srcfile";

    private static final String DEST_DIR_TAG = "destdir";
    private static final String INCLUDE_TAG = "include";
    private static final String EXCLUDE_TAG = "exclude";

	private static final String SOURCE_TAG = "source";
    private static final String TARGET_TAG = "target";
    private static final String ENCODING_TAG = "encoding";

    private static final String CLASS_PATH_TAG = "classpath";
    private static final String BOOT_CLASS_PATH_TAG = "bootclasspath";
    private static final String SRC_PATH_TAG = "sourcepath";

    private static final String ID_ATTR = "id";
    private static final String ERROR_ATTR = "error";
    private static final String STACKTRACE_TAG = "stacktrace";
    

    /** The complete log document for this build. */
    private Document doc = builder.newDocument();

    /** The Message Pattern that we want to start capturing the Javac compilation attributes/parameters*/
    static final Pattern p_compiling_srcfiles = Pattern.compile("^Compiling [1-9][0-9]* source file[s]? to .*");

    /** The Message Pattern that we want to start capturing the Javac compilation arguments*/
    static final Pattern p_compiling_arguments = Pattern.compile("^Compilation arguments:");

    /** The Message Pattern that we want to start capturing the source files that are compiled*/
    static final Pattern p_files_compiled = Pattern.compile("^File[s]? to be compiled:");
    
	private int artifact_count;
	
	//private File projectBaseDir;
    /** Mapping for when targets started (Target to TimedElement). */
 //   private Hashtable<Target, TimedElement> targets = new Hashtable<Target, SwampXmlLogger.TimedElement>();

    /**
     * Mapping of threads to stacks of elements
     * (Thread to Stack of TimedElement).
     */
    private Hashtable<Thread, Stack<Element>> threadStacks = new Hashtable<Thread, Stack<Element>>();

    /**
     * When the build started.
     */
    private Element buildElement = null;

    private enum LogMsgType {
    	COMPILING_XXX_SRC_FILES,
    	COMPILATION_ARGUMENTS,
    	FILES_TOBE_COMPILED,
    	MSG_TYPE_UNKNOWN
    }
    
    /**
     *  Constructs a new BuildListener that logs build events to an XML file.
     */
    public AntBuildListener() {
    }

    /**
     * Fired when the build starts, this builds the top-level element for the
     * document and remembers the time of the start of the build.
     *
     * @param event Ignored.
     */
    public void buildStarted(BuildEvent event) {
        buildElement = doc.createElement(AntBuildListener.BUILD_TAG);
        //buildElement.setAttribute("id", UUID.randomUUID().toString());
        artifact_count = 0;
        //projectBaseDir = event.getProject().getBaseDir();
    }

    /**
     * Fired when the build finishes, this adds the time taken and any
     * error stacktrace to the build element and writes the document to disk.
     *
     * @param event An event with any relevant extra information.
     *              Will not be <code>null</code>.
     */
    public void buildFinished(BuildEvent event) {
        if ((event.getException() != null) && (buildElement != null)) {
            buildElement.setAttribute(ERROR_ATTR, event.getException().toString());
            // print the stacktrace in the build file it is always useful...
            // better have too much info than not enough.
            Throwable t = event.getException();
            Text errText = doc.createCDATASection(StringUtils.getStackTrace(t));
            Element stacktrace = doc.createElement(AntBuildListener.STACKTRACE_TAG);
            stacktrace.appendChild(errText);
            synchronizedAppend(buildElement, stacktrace);
        }
        
        if((buildElement != null) && (buildElement.getChildNodes().getLength() > 0)) {
	        String outFilename = event.getProject().getProperty(LISTENER_OUT_FILENAME_PROP);
	        if (outFilename == null) {
	            outFilename = LISTENER_DEFAULT_OUT_FILENAME;
	        }
	        String xslUri = event.getProject().getProperty("ant.XmlLogger.stylesheet.uri");
	        if (xslUri == null) {
	            xslUri = "log.xsl";
	        }
	        Writer out = null;
	        try {
	            // specify output in UTF8 otherwise accented characters will blow
	            // up everything
	            out = new OutputStreamWriter(new FileOutputStream(outFilename), "UTF8");
	            out.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
	            if (xslUri.length() > 0) {
	                out.write("<?xml-stylesheet type=\"text/xsl\" href=\"" + xslUri + "\"?>\n\n");
	            }
	            new DOMElementWriter().write(buildElement, out, 0, "\t");
	            out.flush();
	        } catch (IOException exc) {
	            throw new BuildException("Unable to write log file", exc);
	        } finally {
	        	FileUtils.close(out);
	        }
        }
        buildElement = null;
    }

    /**
     * Fired when a message is logged, this adds a message element to the
     * most appropriate parent element (task, target or build) and records
     * the priority and text of the message.
     *
     * @param event An event with any relevant extra information.
     *              Will not be <code>null</code>.
     */
    public void messageLogged(BuildEvent event) {
       Throwable ex = event.getException();
        if (ex != null) {
            Text errText = doc.createCDATASection(StringUtils.getStackTrace(ex));
            Element stacktrace = doc.createElement(AntBuildListener.STACKTRACE_TAG);
            stacktrace.appendChild(errText);
            synchronizedAppend(buildElement, stacktrace);
            return;
        }

    	Task task = event.getTask();
    	
    	if ((task != null) && (task instanceof org.apache.tools.ant.taskdefs.Javac)) {

		    switch(getLogMsgType(event.getMessage())) {
		    case COMPILING_XXX_SRC_FILES:
		    	getJavacInfo(event);
                break;		    	
		    //case COMPILATION_ARGUMENTS:
		    //	getCompilationArguments(event);
            //  break;
		    case FILES_TOBE_COMPILED:
		    	getSrcFiles(event);
                break;
		    default:
		    	return;
		    }
    	}
    }

	boolean isaMatch(Pattern pattern, String msg){
    	Matcher matcher = pattern.matcher(msg);
    	//if ((matcher.find() == true) && (matcher.start() == 0) && (matcher.end() == msg.length())){
    	if ((matcher.find() == true) && (matcher.start() == 0)){
    		return true;
    	}
    	return false;
	}

    LogMsgType getLogMsgType(String msg){   	
 
    	if(isaMatch(p_compiling_srcfiles, msg)){
    		return LogMsgType.COMPILING_XXX_SRC_FILES;
    	}else if(isaMatch(p_compiling_arguments, msg)){
    		return LogMsgType.COMPILATION_ARGUMENTS;
    	}else if(isaMatch(p_files_compiled, msg)){
    		return LogMsgType.FILES_TOBE_COMPILED;
    	}
    	
    	return LogMsgType.MSG_TYPE_UNKNOWN;
    }
    
    void getJavacInfo(BuildEvent event) {
    	
		Javac javac = (Javac)event.getTask();
		Element javac_element = doc.createElement(AntBuildListener.TASK_TAG);
		
		/*
	   	Pattern p = Pattern.compile("^Compiling (?<numSrcFiles>[1-9][0-9]*) source file[s]? to .*");
	   	Matcher m = p.matcher(event.getMessage());
	   	if (m.find()){ 
    		javac_element.setAttribute("numSrcFiles", m.group("numSrcFiles"));
    	}*/
		
    	getSrcDir(javac, javac_element);
    	getDestDir(javac, javac_element);
        getIncludeFileFilter(javac, javac_element);
        getExcludeFileFilter(javac, javac_element);
    	getSource(javac, javac_element);
    	getTarget(javac, javac_element);
    	getEncoding(javac, javac_element);
    	getClassPath(javac, javac_element);
    	getBootClassPath(javac, javac_element);
    	getSourcePath(javac, javac_element);
    	
        if(javac_element.getChildNodes().getLength() > 0){
			javac_element.setAttribute(ID_ATTR,  Integer.toString(++artifact_count));
        	synchronizedAppend(buildElement, javac_element);
        }
        
        //This is dangerous, I am changing something in the build.
        if(javac.getDebug() == false) {
        	javac.setDebug(true);
        }
        
    	if(javac.getDebugLevel() != null) {
    		javac.setDebugLevel("vars,lines,source");
    	}
    }

    private void getSrcFiles(BuildEvent event) {
		String msg = event.getMessage();
		String[] files_list = msg.split("\\n");
		Element srcFileElement = doc.createElement(AntBuildListener.SRC_FILE_TAG);
		
		for (int i = 1; i < files_list.length; ++i){
			addFileElement(files_list[i].trim(), srcFileElement);
		}
		
		Element javac_element = (Element)buildElement.getLastChild();
		javac_element.appendChild(srcFileElement);
	}

	private void getCompilationArguments(BuildEvent event) {
		String msg = event.getMessage();
		String[] args = msg.split("\\n");
		Element cli_args = doc.createElement("cmd-line-args");
		
		for (int i = 1; i < args.length; ++i){
			Element arg = doc.createElement("arg");
			arg.appendChild(doc.createCDATASection(args[i].trim()));
			cli_args.appendChild(arg);
		}
		
		buildElement.getLastChild().appendChild(cli_args);
	}
    
    String getAttribute(Hashtable<String, Object> attributes, String name, Project project) {
    	
    	if(attributes.containsKey(name)) {
	    	Object attrib_value = attributes.get(name);
	    	//value = project.getProperty(propertyName)getPropertyHelper(project).getProperty(attrib_value.toString());
	    	//value = project.getProperty(attrib_value.toString());
	    	String value = attrib_value.toString();
	    	/*
            if (attrib_value instanceof Evaluable) {
            	value = ((Evaluable) attrib_value).eval();
            } else {
            	value = PropertyHelper.getPropertyHelper(project).parseProperties(attrib_value.toString());
            	PropertyHelper.getPropertyHelper(project)
            }*/
            if((value != null) && !value.isEmpty()) {
            	return value;
            }else {
            	return null;
            }
    	}else {
    		return null;
    	}
    }
    
    private void addXmlElement(Element parent_element, String name, String value) {
        Element element = doc.createElement(name);
        element.appendChild(doc.createCDATASection(value));
        synchronizedAppend(parent_element, element);   	
    }
    
    private void addFileElement(String filePath, Element parentElement) {
    	addXmlElement(parentElement, "file", filePath);
    }    

    /**
     *  Reads path matching patterns from a file and adds them to the
     *  includes or excludes list (as appropriate).
     */
    private LinkedList<String> readPatterns(String patternFile, Project project)
            throws BuildException {
    	LinkedList<String> filters = null;
        BufferedReader patternReader = null;
        try {
            patternReader = new BufferedReader(new FileReader(project.resolveFile(patternFile)));
            filters = new LinkedList<String>();
            String line = patternReader.readLine();
            while (line != null) {
                if (line.length() > 0) {
                    line = project.replaceProperties(line);
                    filters.add(line);
                }
                line = patternReader.readLine();
            }
        } catch (IOException ioe)  {
            throw new BuildException("An error occurred while reading from pattern file: "
                    + patternFile, ioe);
        } finally {
            FileUtils.close(patternReader);
        }
        
        return filters;
    }

    void getIncludeFileFilter(Javac javac, Element parent_element) {
    	
    	Element includeElement = doc.createElement(AntBuildListener.INCLUDE_TAG);
    	String patternTag = "pattern";

    	for (Enumeration<RuntimeConfigurable> e = javac.getRuntimeConfigurableWrapper().getChildren(); e.hasMoreElements();){
    		RuntimeConfigurable element = e.nextElement();
    		if(element.getElementTag().compareTo("include") == 0){
    			String pattern = getAttribute(element.getAttributeMap(), "name", javac.getProject());
    			if(pattern != null && !pattern.isEmpty()) {
    				addXmlElement(includeElement, patternTag, pattern);
    			}
    		}else if((element.getElementTag().compareTo("patternset") == 0) && 
    					(element.getProxy() instanceof PatternSet)){
    			PatternSet patternset = (PatternSet)element.getProxy();
    			if(patternset.getIncludePatterns(javac.getProject()) != null) {
	    			for(String include_pattern : patternset.getIncludePatterns(javac.getProject())) {
	    				if(!include_pattern.isEmpty()) {
	    					addXmlElement(includeElement, patternTag, include_pattern);
	    				}
	    			}
    			}
    		}
    	}
    	
    	Hashtable<String, Object> attributes = javac.getRuntimeConfigurableWrapper().getAttributeMap();
    	{
    	    String include_pattern = getAttribute(attributes, "includes", javac.getProject());
    	    if(include_pattern != null){
    	    	for(String s : include_pattern.split("[, ]")) {
    	    		if(!s.isEmpty()){
    	    			addXmlElement(includeElement, patternTag, s);
    	    		}
    	    	}
    	    }
    	}    
	 
    	String include_file = getAttribute(attributes, "includesfile", javac.getProject());
	    if(include_file != null){
	    	for(String include_pattern : readPatterns(include_file, javac.getProject())) {
	    		if(!include_pattern.isEmpty()){
	    			addXmlElement(includeElement, patternTag, include_pattern);
	    		}
	    	}
	    }
	    
	    if (includeElement.hasChildNodes()) {
	    	synchronizedAppend(parent_element,  includeElement);
	    }
     }
    
    void getExcludeFileFilter(Javac javac, Element parent_element) {
    	
    	Element excludeElement = doc.createElement(AntBuildListener.EXCLUDE_TAG);
    	String patternTag = "pattern";
    	
    	for (Enumeration<RuntimeConfigurable> e = javac.getRuntimeConfigurableWrapper().getChildren(); e.hasMoreElements();){
    		RuntimeConfigurable element = e.nextElement();
    		if(element.getElementTag().compareTo("exclude") == 0){
    			String exclude_pattern = getAttribute(element.getAttributeMap(), "name", javac.getProject());
    			if(exclude_pattern != null && !exclude_pattern.isEmpty()) {
    				addXmlElement(excludeElement, patternTag, exclude_pattern);
    			}
    		}else if((element.getElementTag().compareTo("patternset") == 0) && 
    					(element.getProxy() instanceof PatternSet)){
    			PatternSet patternset = (PatternSet)element.getProxy();
    			
    			if(patternset.getExcludePatterns(javac.getProject()) != null) {
	    			for(String exclude_pattern : patternset.getExcludePatterns(javac.getProject())) {
	    				if(!exclude_pattern.isEmpty()){
	    					addXmlElement(excludeElement, patternTag, exclude_pattern);
	    				}
	    			}
    			}
    		}
    	}
    	

    	Hashtable<String, Object> attributes = javac.getRuntimeConfigurableWrapper().getAttributeMap();
	    {
	    	String exclude_pattern = getAttribute(attributes, "excludes", javac.getProject());
	    
    	    if(exclude_pattern != null){
    	    	for(String s : exclude_pattern.split("[, ]")) {
    	    		if(!s.isEmpty()){
    	    			addXmlElement(excludeElement, patternTag, s);
    	    		}
    	    	}
    	    }
	    }
	    
	    String exclude_file = getAttribute(attributes, "excludesfile", javac.getProject());
	    if(exclude_file != null){
	    	for(String exclude_pattern : readPatterns(exclude_file, javac.getProject())) {
	    		if(!exclude_pattern.isEmpty()){
	    			addXmlElement(excludeElement, patternTag, exclude_pattern);
	    		}
	    	}
	    }
	    
	    if (excludeElement.hasChildNodes()) {
	    	synchronizedAppend(parent_element,  excludeElement);
	    }
     }
    
    void getSrcDir(Javac javac, Element parent_element) {
        String[] fileList = javac.getSrcdir().list();

		if (fileList.length > 0) {
			Element srcDirElement = doc.createElement(AntBuildListener.SRC_DIR_TAG);        
			for (int i = 0; i < fileList.length; i++) {
				File srcDir = javac.getProject().resolveFile(fileList[i]);
				addFileElement(srcDir.getPath(), srcDirElement);
			}
            synchronizedAppend(parent_element, srcDirElement);
		}
    }
    
    void getDestDir(Javac javac, Element parent_element) {
    	if(javac.getDestdir() != null) {
	        Element destDirElement = doc.createElement(AntBuildListener.DEST_DIR_TAG);
			addFileElement(javac.getDestdir().getPath(), destDirElement);
			synchronizedAppend(parent_element, destDirElement);
    	}
    }
    
    void getClassPath(Javac javac, Element parent_element) {
    	
    	String[] fileList = getCompileClasspath(javac).list();
    	if (fileList.length > 0) {
    		Element messageElement = doc.createElement(AntBuildListener.CLASS_PATH_TAG);
    	for (int i = 0; i < fileList.length; i++) {
            File libFile = javac.getProject().resolveFile(fileList[i]);
            addFileElement(libFile.getPath(), messageElement);
        }
    	synchronizedAppend(parent_element, messageElement);
    	}
    }
    
    
    void getSourcePath(Javac javac, Element parent_element) {
        /*
         * Path sourcepath = null;
        if (javac.getSourcepath() != null) {
            sourcepath = javac.getSourcepath();
        } else {
            sourcepath = javac.getSrcdir();
        }
        
        String[] list = sourcepath.list();
        for (int i = 0; i < list.length; i++) {
            File srcDir = javac.getProject().resolveFile(list[i]);
            Element messageElement = doc.createElement(AntBuildListener.SRC_PATH_TAG);
			messageElement.appendChild(doc.createCDATASection(srcDir.getPath()));
            synchronizedAppend(parent_element, messageElement);
        }
        */
        if ((javac.getSourcepath() != null) && 
        		(javac.getSourcepath().list().length > 0)) {
        	Path sourcepath = javac.getSourcepath();
	        String[] fileList = sourcepath.list();

	        Element srcPathElement = doc.createElement(AntBuildListener.SRC_PATH_TAG);
	        for (int i = 0; i < fileList.length; i++) {
	            File srcDir = javac.getProject().resolveFile(fileList[i]);
				addFileElement(srcDir.getPath(), srcPathElement);
	        }
	        synchronizedAppend(parent_element, srcPathElement);
        }
    }
    
    /**
     * Combines a user specified bootclasspath with the system
     * bootclasspath taking build.sysclasspath into account.
     *
     * @return a non-null Path instance that combines the user
     * specified and the system bootclasspath.
     */
    protected void getBootClassPath(Javac javac, Element parent_element) {
       
        if (javac.getBootclasspath() != null) {
        	Path bp = new Path(javac.getProject());
        	bp.append(javac.getBootclasspath());
            bp.concatSystemBootClasspath("ignore");
            if ((bp.size() > 0) && (bp.list().length > 0)) {
            	
                String[] list = bp.list();
                Element bootClassPathElement = doc.createElement(AntBuildListener.BOOT_CLASS_PATH_TAG);
                for (int i = 0; i < list.length; i++) {
                    File bootclasspath = javac.getProject().resolveFile(list[i]);          
					addFileElement(bootclasspath.getPath(), bootClassPathElement);
                }
                synchronizedAppend(parent_element, bootClassPathElement);
            }
        }
    }

    void getEncoding(Javac javac, Element parent_element) {
        if (javac.getEncoding() != null) {
            Element messageElement = doc.createElement(AntBuildListener.ENCODING_TAG);
            messageElement.appendChild(doc.createCDATASection(javac.getEncoding()));
            synchronizedAppend(parent_element, messageElement);
        }
    }
    
	/**
	 * Turn the task's attribute for -source into soemthing that is
	 * understood by all javac's after 1.4.
	 *
	 * <p>support for -source 1.1 and -source 1.2 has been added with
	 * JDK 1.4.2 but isn't present in 1.5.0+</p>
	 */
	private String adjustSourceValue(String source) {
	    return (source.equals("1.1") || source.equals("1.2")) ? "1.3" : source;
	}
	
    /**
     * Shall we assume command line switches for the given version of Java?
     * @since Ant 1.8.3
     */
    private boolean assumeJavaXY(String javacXY, String javaEnvVersionXY, Javac javac) {
        return javacXY.equals(javac.getCompilerVersion())
            || ("classic".equals(javac.getCompilerVersion())
                && JavaEnvUtils.isJavaVersion(javaEnvVersionXY))
            || ("modern".equals(javac.getCompilerVersion())
                && JavaEnvUtils.isJavaVersion(javaEnvVersionXY))
            || ("extJavac".equals(javac.getCompilerVersion())
                && JavaEnvUtils.isJavaVersion(javaEnvVersionXY));
    }


    /**
     * Shall we assume JDK 1.4 command line switches?
     * @return true if jdk 1.4
     * @since Ant 1.6.3
     */
    protected boolean assumeJava14(Javac javac) {
        return assumeJavaXY("javac1.4", JavaEnvUtils.JAVA_1_4, javac);
    }

    /**
     * Shall we assume JDK 1.5 command line switches?
     * @return true if JDK 1.5
     * @since Ant 1.6.3
     */
    protected boolean assumeJava15(Javac javac) {
        return assumeJavaXY("javac1.5", JavaEnvUtils.JAVA_1_5, javac);
    }

    /**
     * Shall we assume JDK 1.6 command line switches?
     * @return true if JDK 1.6
     * @since Ant 1.7
     */
    protected boolean assumeJava16(Javac javac) {
        return assumeJavaXY("javac1.6", JavaEnvUtils.JAVA_1_6, javac);
    }

    /**
     * Shall we assume JDK 1.7 command line switches?
     * @return true if JDK 1.7
     * @since Ant 1.8.2

    protected boolean assumeJava17(Javac javac) {
        return assumeJavaXY("javac1.7", JavaEnvUtils.JAVA_1_7, javac);
    }*/
    
    /**
     * Shall we assume JDK 1.8 command line switches?
     * @return true if JDK 1.8
     * @since Ant 1.8.3
     
    protected boolean assumeJava18(Javac javac) {
        return assumeJavaXY("javac1.8", JavaEnvUtils.JAVA_1_8, javac);
    }*/

	
	/**
	 * Whether the selected -target is known to be incompatible with
	 * the default -source value of the selected JDK's javac.
	 *
	 * <p>Assumes it will never be called unless the selected JDK is
	 * at least Java 1.5.</p>
	 *
	 * @param t the -target value, must not be null
	 */
	private boolean mustSetSourceForTarget(String t, Javac javac) {
	    if (assumeJava14(javac)) {
	        return false;
	    }
	    if (t.startsWith("1.")) {
	        t = t.substring(2);
	    }
	    return t.equals("1") || t.equals("2") || t.equals("3") || t.equals("4")
	        || ((t.equals("5") || t.equals("6"))
	            && !assumeJava15(javac) && !assumeJava16(javac))
	        || (t.equals("7")); // && !assumeJava17(javac));
	}

     protected void getTarget(Javac javac, Element parent_element) {    	 
	    if (javac.getTarget() != null) {
	    	Element messageElement = doc.createElement(AntBuildListener.TARGET_TAG);
            messageElement.appendChild(doc.createCDATASection(javac.getTarget()));
            synchronizedAppend(parent_element, messageElement);
            
            if(mustSetSourceForTarget(javac.getTarget(), javac)){
    	    	messageElement = doc.createElement(AntBuildListener.SOURCE_TAG);
                messageElement.appendChild(doc.createCDATASection(adjustSourceValue(javac.getTarget())));
                synchronizedAppend(parent_element, messageElement);            	
            }
        }
    }

    protected void getSource(Javac javac, Element parent_element) {    	 
	    if (javac.getSource() != null) {
	    	Element messageElement = doc.createElement(AntBuildListener.SOURCE_TAG);
            messageElement.appendChild(doc.createCDATASection(adjustSourceValue(javac.getSource())));
            synchronizedAppend(parent_element, messageElement);
        }
    }

    protected Path getCompileClasspath(Javac javac) {
        Path classpath = new Path(javac.getProject());

        if (javac.getDestdir() != null && javac.isIncludeDestClasses()) {
            classpath.setLocation(javac.getDestdir());
        }

        Path cp = javac.getClasspath();
        if (cp == null) {
            cp = new Path(javac.getProject());
        }
        if (javac.getIncludeantruntime()) {
            classpath.addExisting(cp.concatSystemClasspath("last"));
        } else {
            classpath.addExisting(cp.concatSystemClasspath("ignore"));
        }

        if (javac.getIncludejavaruntime()) {
            classpath.addJavaRuntime();
        }

        return classpath;
    }

    private void synchronizedAppend(Node parent, Node child) {
        synchronized(parent) {
            parent.appendChild(child);
        }
    }

	@Override
	public void targetStarted(BuildEvent event) {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void targetFinished(BuildEvent event) {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void taskStarted(BuildEvent event) {
		// TODO Auto-generated method stub
		
	}

	@Override
	public void taskFinished(BuildEvent event) {
		// TODO Auto-generated method stub
		
	}

}
